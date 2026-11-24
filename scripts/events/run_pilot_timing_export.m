function [events, validation] = run_pilot_timing_export(configPath, outputDirectory)
%RUN_PILOT_TIMING_EXPORT Run the strict timing export for the pilot subject.
%
%   RUN_PILOT_TIMING_EXPORT() reads config/pilot_sub-MBMF001502.json,
%   validates source checksums and timing-to-behavior trial alignment, and
%   writes these files under derivatives/pilot/sub-MBMF001502
%
%   events_reconstructed.tsv
%   timing_validation.json
%
%   Optional CONFIGPATH and OUTPUTDIRECTORY arguments make the wrapper
%   testable without changing its canonical defaults.

    scriptDirectory = fileparts(mfilename('fullpath'));
    repositoryRoot = fileparts(fileparts(scriptDirectory));
    addpath(scriptDirectory);
    pathCleanup = onCleanup(@() rmpath(scriptDirectory));

    if nargin < 1 || isempty(configPath)
        configPath = fullfile(repositoryRoot, 'config', ...
            'pilot_sub-MBMF001502.json');
    else
        configPath = resolve_path(repositoryRoot, configPath);
    end
    if exist(configPath, 'file') ~= 2
        error('ds007474:TimingPilot:MissingConfig', ...
            'Pilot configuration does not exist: %s', configPath);
    end

    configuration = jsondecode(fileread(configPath));
    require_struct_fields(configuration, ...
        {'schema_version', 'participant', 'sources', 'run_mapping'}, ...
        'pilot configuration');
    require_struct_fields(configuration.participant, ...
        {'timing_subject_id', 'timing_session_id', 'openneuro_id'}, ...
        'participant configuration');
    require_struct_fields(configuration.sources, {'timing', 'behavior'}, ...
        'source configuration');
    require_struct_fields(configuration.sources.timing, {'path', 'sha256'}, ...
        'timing source configuration');
    require_struct_fields(configuration.sources.behavior, {'path', 'sha256'}, ...
        'behavior source configuration');

    participantID = char(string(configuration.participant.openneuro_id));
    timingPath = resolve_path(repositoryRoot, configuration.sources.timing.path);
    behaviorPath = resolve_path(repositoryRoot, configuration.sources.behavior.path);
    if nargin < 2 || isempty(outputDirectory)
        outputDirectory = fullfile(repositoryRoot, 'derivatives', 'pilot', ...
            participantID);
    else
        outputDirectory = resolve_path(repositoryRoot, outputDirectory);
    end

    assert_source_checksum(timingPath, configuration.sources.timing.sha256, ...
        'timing');
    assert_source_checksum(behaviorPath, configuration.sources.behavior.sha256, ...
        'behavior');

    mappings = configuration.run_mapping;
    if ~isstruct(mappings) || isempty(mappings)
        error('ds007474:TimingPilot:RunMapping', ...
            'run_mapping must be a nonempty structure array.');
    end
    timingRunIDs = [mappings.timing_run_id];
    behaviorRunIDs = [mappings.behavior_run_id];
    behaviorRunOffsets = behaviorRunIDs - timingRunIDs;
    if numel(unique(behaviorRunOffsets)) ~= 1
        error('ds007474:TimingPilot:RunMapping', ...
            'Every pilot run must use the same behavior-to-timing run offset.');
    end
    behaviorRunOffset = behaviorRunOffsets(1);
    trialCounts = [mappings.last_functional_trial_id] ...
        - [mappings.first_functional_trial_id] + 1;
    if numel(unique(trialCounts)) ~= 1
        error('ds007474:TimingPilot:RunMapping', ...
            'Every pilot timing run must have the same configured trial count.');
    end

    behaviorCrosscheck = crosscheck_behavior(timingPath, behaviorPath, mappings);
    if ~behaviorCrosscheck.passed
        error('ds007474:TimingPilot:BehaviorMismatch', ...
            'Timing-to-behavior trial cross-check failed: %s', ...
            strjoin(behaviorCrosscheck.failed_checks, ', '));
    end

    if exist(outputDirectory, 'dir') ~= 7
        [madeDirectory, message] = mkdir(outputDirectory);
        if ~madeDirectory
            error('ds007474:TimingPilot:OutputDirectory', ...
                'Could not create output directory %s: %s', ...
                outputDirectory, message);
        end
    end
    eventsPath = fullfile(outputDirectory, 'events_reconstructed.tsv');
    validationPath = fullfile(outputDirectory, 'timing_validation.json');

    [events, validation] = export_osf_timings(timingPath, eventsPath, ...
        'ExpectedParticipantID', participantID, ...
        'ExpectedSourceSubjectID', ...
            configuration.participant.timing_subject_id, ...
        'ExpectedSourceSessionID', ...
            configuration.participant.timing_session_id, ...
        'BehaviorRunOffset', behaviorRunOffset, ...
        'ExpectedNumberOfRuns', numel(mappings), ...
        'ExpectedTrialsPerRun', trialCounts(1));

    validation.config_path = configPath;
    validation.config_schema_version = char(string(configuration.schema_version));
    validation.source_checksums = struct();
    validation.source_checksums.timing_sha256 = ...
        char(lower(string(configuration.sources.timing.sha256)));
    validation.source_checksums.behavior_sha256 = ...
        char(lower(string(configuration.sources.behavior.sha256)));
    validation.behavior_crosscheck = behaviorCrosscheck;
    validation.behavior_crosscheck_passed = behaviorCrosscheck.passed;
    validation.assumptions.behavior_outcome_mapping = ...
        ['raw timing outcome1 is landing pad 1 to 4 and equals behavior ' ...
         'outcome2; behavior outcome1 is planet 1 for pads 1 or 2 and ' ...
         'planet 2 for pads 3 or 4 on observed landing trials'];
    validation.assumptions.raw_timing_outcome2 = ...
        'raw timing outcome2 is unused and entirely missing';

    write_json_atomic(validation, validationPath);

    fprintf(['Exported %d events for %s to %s. Behavior alignment passed ' ...
        'for %d functional trials, including %d missed response.\n'], ...
        height(events), participantID, eventsPath, ...
        behaviorCrosscheck.functional_trial_count, ...
        behaviorCrosscheck.missed_response_count);

    clear pathCleanup;
end


function crosscheck = crosscheck_behavior(timingPath, behaviorPath, mappings)
    timingSource = load(timingPath, 'task_MBMF_fMRI');
    timing = timingSource.task_MBMF_fMRI.trials;
    behavior = readtable(behaviorPath, 'TextType', 'string');

    requiredTiming = {'trialID', 'runID', 'resp1', 'RT1', 'outcome1', ...
        'outcome2', 'outcomeBin', 'outcomeMag', 'doRareTrans'};
    missingTiming = setdiff(requiredTiming, timing.Properties.VariableNames);
    if ~isempty(missingTiming)
        error('ds007474:TimingPilot:TimingColumns', ...
            'Timing table is missing columns: %s', strjoin(missingTiming, ', '));
    end
    requiredBehavior = {'runID', 'sess_type', 'trialID', 'Resp1', 'RT1', ...
        'outcome1', 'outcome2', 'outcomeBin', 'outcomeMag', 'doRareTrans'};
    missingBehavior = setdiff(requiredBehavior, behavior.Properties.VariableNames);
    if ~isempty(missingBehavior)
        error('ds007474:TimingPilot:BehaviorColumns', ...
            'Behavior table is missing columns: %s', ...
            strjoin(missingBehavior, ', '));
    end

    functionalMask = lower(strtrim(string(behavior.sess_type))) == "functional";
    functional = behavior(functionalMask, :);
    expectedTrialCount = sum([mappings.last_functional_trial_id] ...
        - [mappings.first_functional_trial_id] + 1);
    if height(functional) ~= expectedTrialCount || height(timing) ~= expectedTrialCount
        error('ds007474:TimingPilot:FunctionalTrialCount', ...
            ['Behavior contains %d functional rows and timing contains %d rows; ' ...
             'configuration expects %d.'], ...
            height(functional), height(timing), expectedTrialCount);
    end

    expectedBehaviorRun = nan(height(timing), 1);
    mappingBoundariesPass = true;
    for mappingIndex = 1:numel(mappings)
        mapping = mappings(mappingIndex);
        timingRows = double(timing.runID) == mapping.timing_run_id;
        expectedBehaviorRun(timingRows) = mapping.behavior_run_id;
        mappedTrialIDs = double(timing.trialID(timingRows));
        expectedIDs = (mapping.first_functional_trial_id: ...
            mapping.last_functional_trial_id)';
        mappingBoundariesPass = mappingBoundariesPass ...
            && isequal(mappedTrialIDs, expectedIDs);
    end

    [trialIDPass, trialIDError] = numeric_match( ...
        timing.trialID, functional.trialID, true(height(timing), 1), 0);
    [runIDPass, runIDError] = numeric_match( ...
        expectedBehaviorRun, functional.runID, true(height(timing), 1), 0);
    [responsePass, responseError] = numeric_match( ...
        timing.resp1, functional.Resp1, true(height(timing), 1), 1e-12);
    [reactionTimePass, reactionTimeError] = numeric_match( ...
        timing.RT1, functional.RT1, true(height(timing), 1), 1e-9);
    [rareTransitionPass, rareTransitionError] = numeric_match( ...
        timing.doRareTrans, functional.doRareTrans, ...
        true(height(timing), 1), 0);
    [outcomeBinPass, outcomeBinError] = numeric_match( ...
        timing.outcomeBin, functional.outcomeBin, ...
        true(height(timing), 1), 1e-12);
    [outcomeMagnitudePass, outcomeMagnitudeError] = numeric_match( ...
        timing.outcomeMag, functional.outcomeMag, ...
        true(height(timing), 1), 1e-9);

    % The task calls the observed landing pad outcome1. The behavioral
    % conversion renames that same 1-to-4 value outcome2.
    [landingPadPass, landingPadError] = numeric_match( ...
        timing.outcome1, functional.outcome2, ...
        true(height(timing), 1), 1e-12);

    % The behavioral outcome1 is a derived planet label. It has a value on
    % the missed trial even though no landing event was observed, so compare
    % it only where the raw timing file contains an observed landing pad.
    observedLanding = isfinite(double(timing.outcome1));
    derivedPlanet = nan(height(timing), 1);
    timingLandingPad = double(timing.outcome1);
    derivedPlanet(ismember(timingLandingPad, [1 2])) = 1;
    derivedPlanet(ismember(timingLandingPad, [3 4])) = 2;
    validLandingCodes = isnan(timingLandingPad) ...
        | ismember(timingLandingPad, 1:4);
    [planetPass, planetError] = numeric_match( ...
        derivedPlanet, functional.outcome1, observedLanding, 1e-12);
    planetPass = planetPass && all(validLandingCodes);

    timingMissed = isnan(double(timing.resp1));
    behaviorMissed = isnan(double(functional.Resp1));
    missedResponsePass = isequal(timingMissed, behaviorMissed);
    timingOutcome2Unused = all(isnan(double(timing.outcome2)));

    checkNames = {'mapping_boundaries', 'trial_id', 'run_id', 'response', ...
        'reaction_time', 'rare_transition', 'binary_outcome', ...
        'outcome_magnitude', 'landing_pad_outcome2', ...
        'derived_planet_outcome1_observed', 'missed_response_pattern', ...
        'raw_timing_outcome2_unused'};
    checkValues = [mappingBoundariesPass, trialIDPass, runIDPass, ...
        responsePass, reactionTimePass, rareTransitionPass, ...
        outcomeBinPass, outcomeMagnitudePass, landingPadPass, planetPass, ...
        missedResponsePass, timingOutcome2Unused];

    crosscheck = struct();
    crosscheck.passed = all(checkValues);
    crosscheck.failed_checks = checkNames(~checkValues);
    crosscheck.functional_trial_count = height(functional);
    crosscheck.observed_landing_trial_count = sum(observedLanding);
    crosscheck.derived_planet_skipped_trial_count = sum(~observedLanding);
    crosscheck.missed_response_count = sum(timingMissed);
    crosscheck.missed_response_trial_ids = ...
        double(timing.trialID(timingMissed))';
    crosscheck.mapping_boundaries_match = mappingBoundariesPass;
    crosscheck.trial_id_match = trialIDPass;
    crosscheck.behavior_run_id_match = runIDPass;
    crosscheck.response_match = responsePass;
    crosscheck.reaction_time_match = reactionTimePass;
    crosscheck.rare_transition_match = rareTransitionPass;
    crosscheck.binary_outcome_match = outcomeBinPass;
    crosscheck.outcome_magnitude_match = outcomeMagnitudePass;
    crosscheck.timing_outcome1_matches_behavior_outcome2 = landingPadPass;
    crosscheck.derived_planet_matches_behavior_outcome1_on_observed_trials = ...
        planetPass;
    crosscheck.missed_response_pattern_match = missedResponsePass;
    crosscheck.raw_timing_outcome2_all_missing = timingOutcome2Unused;
    crosscheck.maximum_absolute_errors = struct( ...
        'trial_id', trialIDError, 'run_id', runIDError, ...
        'response', responseError, 'reaction_time', reactionTimeError, ...
        'rare_transition', rareTransitionError, ...
        'binary_outcome', outcomeBinError, ...
        'outcome_magnitude', outcomeMagnitudeError, ...
        'landing_pad_outcome2', landingPadError, ...
        'derived_planet_outcome1_observed', planetError);
    crosscheck.outcome_mapping = ...
        ['timing outcome1 equals behavior outcome2; behavior outcome1 is ' ...
         'derived as planet 1 for pads 1 or 2 and planet 2 for pads 3 or 4'];
    crosscheck.outcome1_missed_trial_policy = ...
        ['skip derived behavior outcome1 comparison when raw timing ' ...
         'outcome1 is unavailable after a missed response'];
end


function [passed, maximumError] = numeric_match(actual, expected, mask, tolerance)
    actual = double(actual(:));
    expected = double(expected(:));
    mask = logical(mask(:));
    if numel(actual) ~= numel(expected) || numel(mask) ~= numel(actual)
        passed = false;
        maximumError = Inf;
        return;
    end
    actual = actual(mask);
    expected = expected(mask);
    sameMissing = isnan(actual) & isnan(expected);
    bothFinite = isfinite(actual) & isfinite(expected);
    matches = sameMissing | (bothFinite & abs(actual - expected) <= tolerance);
    passed = all(matches);
    finiteDifferences = abs(actual(bothFinite) - expected(bothFinite));
    if isempty(finiteDifferences)
        maximumError = 0;
    else
        maximumError = max(finiteDifferences);
    end
end


function assert_source_checksum(pathName, expectedChecksum, sourceLabel)
    if exist(pathName, 'file') ~= 2
        error('ds007474:TimingPilot:MissingSource', ...
            'Configured %s source does not exist: %s', sourceLabel, pathName);
    end
    expectedChecksum = lower(char(string(expectedChecksum)));
    observedChecksum = sha256_file(pathName);
    if ~strcmp(observedChecksum, expectedChecksum)
        error('ds007474:TimingPilot:ChecksumMismatch', ...
            ['%s source checksum mismatch for %s. Expected %s but ' ...
             'observed %s.'], ...
            sourceLabel, pathName, expectedChecksum, observedChecksum);
    end
end


function checksum = sha256_file(pathName)
    digest = java.security.MessageDigest.getInstance('SHA-256');
    fileID = fopen(pathName, 'rb');
    if fileID < 0
        error('ds007474:TimingPilot:SourceRead', ...
            'Could not open source file for hashing: %s', pathName);
    end
    fileCleanup = onCleanup(@() fclose(fileID));
    while ~feof(fileID)
        bytes = fread(fileID, 1024 * 1024, '*uint8');
        if ~isempty(bytes)
            digest.update(bytes);
        end
    end
    checksum = lower(reshape(dec2hex(typecast(digest.digest(), 'uint8'), 2).', ...
        1, []));
    clear fileCleanup;
end


function write_json_atomic(value, outputPath)
    outputDirectory = fileparts(outputPath);
    temporaryPath = [tempname(outputDirectory) '.json'];
    temporaryCleanup = onCleanup(@() delete_if_present(temporaryPath));
    fileID = fopen(temporaryPath, 'w');
    if fileID < 0
        error('ds007474:TimingPilot:JSONWrite', ...
            'Could not open temporary JSON output: %s', temporaryPath);
    end
    fileCleanup = onCleanup(@() fclose(fileID));
    bytesWritten = fwrite(fileID, jsonencode(value), 'char');
    if bytesWritten <= 0
        error('ds007474:TimingPilot:JSONWrite', ...
            'No bytes were written to temporary JSON output: %s', temporaryPath);
    end
    clear fileCleanup;
    [moved, message] = movefile(temporaryPath, outputPath, 'f');
    if ~moved
        error('ds007474:TimingPilot:JSONWrite', ...
            'Could not move completed JSON to %s: %s', outputPath, message);
    end
    clear temporaryCleanup;
end


function pathName = resolve_path(repositoryRoot, pathName)
    pathName = char(string(pathName));
    if isempty(pathName)
        error('ds007474:TimingPilot:EmptyPath', ...
            'Configured path must not be empty.');
    end
    isAbsolute = startsWith(pathName, filesep) ...
        || ~isempty(regexp(pathName, '^[A-Za-z]:[\\/]', 'once'));
    if ~isAbsolute
        pathName = fullfile(repositoryRoot, pathName);
    end
end


function require_struct_fields(value, fields, label)
    if ~isstruct(value)
        error('ds007474:TimingPilot:Configuration', ...
            '%s must be a structure.', label);
    end
    missing = fields(~isfield(value, fields));
    if ~isempty(missing)
        error('ds007474:TimingPilot:Configuration', ...
            '%s is missing fields: %s', label, strjoin(missing, ', '));
    end
end


function delete_if_present(pathName)
    if exist(pathName, 'file') == 2
        delete(pathName);
    end
end
