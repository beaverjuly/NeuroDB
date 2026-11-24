function [events, validation] = export_osf_timings(inputMat, outputTsv, varargin)
%EXPORT_OSF_TIMINGS Export scanner-relative task events from an OSF MAT file.
%
%   [EVENTS, VALIDATION] = EXPORT_OSF_TIMINGS(INPUTMAT, OUTPUTTSV) loads the
%   task_MBMF_fMRI structure saved by the original task and writes a
%   normalized, long-format TSV. One row represents one observed event.
%
%   This exporter intentionally uses MATLAB to decode the MATLAB table in
%   the source file. It does not modify the author-code submodule.
%
%   Name-value options
%
%   ExpectedParticipantID    OpenNeuro ID, for example sub-MBMF001502
%   ExpectedSourceSubjectID  Numeric or text OSF subject ID
%   ExpectedSourceSessionID  Numeric or text OSF session/order ID
%   BehaviorRunOffset        task run + offset gives behavioral run ID
%                            default 1 because run 1 in the behavioral CSV
%                            is the structural session
%   ExpectedNumberOfRuns     default 2
%   ExpectedTrialsPerRun     default 77
%   TimingTolerance          seconds, default 1e-6
%
%   Event mapping, established from the original task code
%
%   fixation          tStart
%   stimulus          tStim1On
%   response_left     tResp1 when resp1 is 1
%   response_right    tResp1 when resp1 is 2
%   response_missing  tResp1 when resp1 is NaN
%   planet            tState2On
%   pad               tTerminalState2On
%   outcome           tFBOn_Bin, checked against tFBOn_Mag
%
%   Every onset is source_timestamp minus tRunStart for that task run. All
%   durations are zero because these events are intended as stick functions
%   in the published first-level model. A missed response retains fixation,
%   stimulus, and response_missing rows; unavailable downstream events are
%   not fabricated.

    parser = inputParser;
    parser.FunctionName = mfilename;
    addRequired(parser, 'inputMat', @(x) ischar(x) || (isstring(x) && isscalar(x)));
    addRequired(parser, 'outputTsv', @(x) ischar(x) || (isstring(x) && isscalar(x)));
    addParameter(parser, 'ExpectedParticipantID', '', ...
        @(x) ischar(x) || (isstring(x) && isscalar(x)));
    addParameter(parser, 'ExpectedSourceSubjectID', [], ...
        @(x) isempty(x) || isnumeric(x) || ischar(x) || (isstring(x) && isscalar(x)));
    addParameter(parser, 'ExpectedSourceSessionID', [], ...
        @(x) isempty(x) || isnumeric(x) || ischar(x) || (isstring(x) && isscalar(x)));
    addParameter(parser, 'BehaviorRunOffset', 1, ...
        @(x) isnumeric(x) && isscalar(x) && isfinite(x) && x == round(x));
    addParameter(parser, 'ExpectedNumberOfRuns', 2, ...
        @(x) isempty(x) || (isnumeric(x) && isscalar(x) && isfinite(x) && x > 0 && x == round(x)));
    addParameter(parser, 'ExpectedTrialsPerRun', 77, ...
        @(x) isempty(x) || (isnumeric(x) && isscalar(x) && isfinite(x) && x > 0 && x == round(x)));
    addParameter(parser, 'TimingTolerance', 1e-6, ...
        @(x) isnumeric(x) && isscalar(x) && isfinite(x) && x >= 0);
    parse(parser, inputMat, outputTsv, varargin{:});
    options = parser.Results;

    inputMat = char(inputMat);
    outputTsv = char(outputTsv);
    tolerance = options.TimingTolerance;

    if exist(inputMat, 'file') ~= 2
        error('ds007474:Timing:MissingInput', ...
            'OSF timing file does not exist: %s', inputMat);
    end

    loaded = load(inputMat);
    if ~isfield(loaded, 'task_MBMF_fMRI') || ~isstruct(loaded.task_MBMF_fMRI) ...
            || ~isscalar(loaded.task_MBMF_fMRI)
        error('ds007474:Timing:MissingTaskStruct', ...
            'Expected one task_MBMF_fMRI structure in %s.', inputMat);
    end
    task = loaded.task_MBMF_fMRI;

    requiredTaskFields = {'subID', 'orderID', 'fileName', 'trials', ...
        'tRunStart', 'tRunEnd'};
    require_fields(task, requiredTaskFields, 'task_MBMF_fMRI');
    if ~istable(task.trials)
        error('ds007474:Timing:InvalidTrials', ...
            'task_MBMF_fMRI.trials must be a MATLAB table.');
    end
    trials = task.trials;

    requiredTrialFields = {'trialID', 'runID', 'resp1', 'RT1', ...
        'tStart', 'tFixOn', 'tStim1On', 'tResp1', 'tState2On', ...
        'tTerminalState2On', 'tFBOn_Bin', 'tFBOn_Mag'};
    missingTrialFields = setdiff(requiredTrialFields, trials.Properties.VariableNames);
    if ~isempty(missingTrialFields)
        error('ds007474:Timing:MissingTrialFields', ...
            'Missing trial fields: %s', strjoin(missingTrialFields, ', '));
    end

    sourceSubject = integer_id(task.subID, 'task_MBMF_fMRI.subID');
    sourceSession = integer_id(task.orderID, 'task_MBMF_fMRI.orderID');

    if isfield(loaded, 'subID')
        topSubject = integer_id(loaded.subID, 'top-level subID');
        assert_equal_id(topSubject, sourceSubject, 'top-level subID', ...
            'task_MBMF_fMRI.subID');
    else
        error('ds007474:Timing:MissingTopLevelSubject', ...
            'The source MAT lacks the redundant top-level subID check.');
    end
    if isfield(loaded, 'orderID')
        topSession = integer_id(loaded.orderID, 'top-level orderID');
        assert_equal_id(topSession, sourceSession, 'top-level orderID', ...
            'task_MBMF_fMRI.orderID');
    else
        error('ds007474:Timing:MissingTopLevelSession', ...
            'The source MAT lacks the redundant top-level orderID check.');
    end

    [~, inputBase, inputExtension] = fileparts(inputMat);
    inputTokens = parse_source_filename([inputBase inputExtension]);
    assert_equal_id(inputTokens.subject, sourceSubject, 'input filename subject', ...
        'task_MBMF_fMRI.subID');
    assert_equal_id(inputTokens.session, sourceSession, 'input filename session', ...
        'task_MBMF_fMRI.orderID');

    taskTokens = parse_source_filename(char(string(task.fileName)));
    assert_equal_id(taskTokens.subject, sourceSubject, 'task fileName subject', ...
        'task_MBMF_fMRI.subID');
    assert_equal_id(taskTokens.session, sourceSession, 'task fileName session', ...
        'task_MBMF_fMRI.orderID');

    if ~isempty(options.ExpectedSourceSubjectID)
        expectedSubject = integer_id(options.ExpectedSourceSubjectID, ...
            'ExpectedSourceSubjectID');
        assert_equal_id(sourceSubject, expectedSubject, 'source subject', ...
            'ExpectedSourceSubjectID');
    end
    if ~isempty(options.ExpectedSourceSessionID)
        expectedSession = integer_id(options.ExpectedSourceSessionID, ...
            'ExpectedSourceSessionID');
        assert_equal_id(sourceSession, expectedSession, 'source session', ...
            'ExpectedSourceSessionID');
    end

    canonicalParticipant = string(sprintf('sub-MBMF%04d%02d', ...
        sourceSubject, sourceSession));
    expectedParticipant = strtrim(string(options.ExpectedParticipantID));
    if strlength(expectedParticipant) > 0 && canonicalParticipant ~= expectedParticipant
        error('ds007474:Timing:ParticipantMismatch', ...
            ['Derived OpenNeuro participant %s from source subject %04d and ' ...
             'session %d, but ExpectedParticipantID is %s.'], ...
            canonicalParticipant, sourceSubject, sourceSession, expectedParticipant);
    end

    numericTrialFields = setdiff(requiredTrialFields, {'tFixOn'});
    for fieldIndex = 1:numel(numericTrialFields)
        fieldName = numericTrialFields{fieldIndex};
        values = trials.(fieldName);
        if ~isnumeric(values) || ~isvector(values) || numel(values) ~= height(trials)
            error('ds007474:Timing:InvalidTrialField', ...
                'Trial field %s must be a numeric vector with one value per trial.', ...
                fieldName);
        end
    end
    if ~isnumeric(trials.tFixOn) || ~isvector(trials.tFixOn) ...
            || numel(trials.tFixOn) ~= height(trials)
        error('ds007474:Timing:InvalidTrialField', ...
            'Trial field tFixOn must be a numeric vector with one value per trial.');
    end

    numberOfTrials = height(trials);
    expectedTrialIDs = (1:numberOfTrials)';
    if any(~isfinite(trials.trialID)) || ...
            ~isequal(double(trials.trialID(:)), double(expectedTrialIDs))
        error('ds007474:Timing:TrialOrder', ...
            'trialID must be the unique, ordered sequence 1 through %d.', numberOfTrials);
    end
    if any(~isfinite(trials.runID)) || any(trials.runID ~= round(trials.runID))
        error('ds007474:Timing:RunID', ...
            'runID must contain finite integer task-run labels.');
    end

    taskRuns = unique(double(trials.runID(:)), 'stable')';
    numberOfRuns = numel(taskRuns);
    if ~isequal(taskRuns, 1:numberOfRuns)
        error('ds007474:Timing:RunOrder', ...
            'Task runs must be contiguous and ordered as 1 through %d.', numberOfRuns);
    end
    if ~isempty(options.ExpectedNumberOfRuns) ...
            && numberOfRuns ~= options.ExpectedNumberOfRuns
        error('ds007474:Timing:RunCount', ...
            'Found %d task runs, expected %d.', ...
            numberOfRuns, options.ExpectedNumberOfRuns);
    end

    runStart = double(task.tRunStart(:));
    runEnd = double(task.tRunEnd(:));
    if numel(runStart) ~= numberOfRuns || numel(runEnd) ~= numberOfRuns ...
            || any(~isfinite(runStart)) || any(~isfinite(runEnd))
        error('ds007474:Timing:RunBounds', ...
            'tRunStart and tRunEnd must each contain one finite value per task run.');
    end
    if any(runEnd <= runStart)
        error('ds007474:Timing:RunBounds', ...
            'Every tRunEnd must be later than its corresponding tRunStart.');
    end
    if numberOfRuns > 1 && any(runStart(2:end) <= runEnd(1:end-1))
        error('ds007474:Timing:RunOverlap', ...
            'Successive task-run intervals must not overlap.');
    end
    runDuration = runEnd - runStart;

    trialInRun = nan(numberOfTrials, 1);
    trialsPerRun = zeros(numberOfRuns, 1);
    for runIndex = 1:numberOfRuns
        runRows = find(trials.runID == runIndex);
        if isempty(runRows) || any(diff(runRows) ~= 1)
            error('ds007474:Timing:RunTrialOrder', ...
                'Trials for task run %d must form one contiguous block.', runIndex);
        end
        trialsPerRun(runIndex) = numel(runRows);
        trialInRun(runRows) = (1:numel(runRows))';
        if ~isempty(options.ExpectedTrialsPerRun) ...
                && numel(runRows) ~= options.ExpectedTrialsPerRun
            error('ds007474:Timing:TrialCount', ...
                'Task run %d has %d trials, expected %d.', ...
                runIndex, numel(runRows), options.ExpectedTrialsPerRun);
        end
    end

    timingFields = {'tStart', 'tStim1On', 'tResp1', 'tState2On', ...
        'tTerminalState2On', 'tFBOn_Bin', 'tFBOn_Mag'};
    for fieldIndex = 1:numel(timingFields)
        values = double(trials.(timingFields{fieldIndex})(:));
        if any(isinf(values))
            error('ds007474:Timing:InfiniteTimestamp', ...
                'Timing field %s contains an infinite value.', timingFields{fieldIndex});
        end
    end
    if any(isfinite(double(trials.tFixOn(:))))
        error('ds007474:Timing:UnexpectedFixationField', ...
            ['tFixOn unexpectedly contains finite values. The task code records ' ...
             'fixation onset in tStart, so this ambiguity requires manual review.']);
    end

    requiredEveryTrial = {'tStart', 'tStim1On', 'tResp1', 'RT1'};
    for fieldIndex = 1:numel(requiredEveryTrial)
        fieldName = requiredEveryTrial{fieldIndex};
        if any(~isfinite(double(trials.(fieldName)(:))))
            error('ds007474:Timing:MissingCoreTimestamp', ...
                'Core trial field %s contains missing or nonfinite values.', fieldName);
        end
    end

    responseCode = double(trials.resp1(:));
    responseMissing = isnan(responseCode);
    invalidResponses = ~(responseMissing | responseCode == 1 | responseCode == 2);
    if any(invalidResponses)
        error('ds007474:Timing:ResponseCode', ...
            'resp1 must be 1 for left, 2 for right, or NaN for a missed response.');
    end

    rtError = abs((double(trials.tResp1(:)) - double(trials.tStim1On(:))) ...
        - double(trials.RT1(:)));
    if any(rtError > tolerance)
        error('ds007474:Timing:ReactionTimeMismatch', ...
            'RT1 disagrees with tResp1 minus tStim1On by more than %.3g seconds.', ...
            tolerance);
    end

    postResponseFields = {'tState2On', 'tTerminalState2On', ...
        'tFBOn_Bin', 'tFBOn_Mag'};
    for fieldIndex = 1:numel(postResponseFields)
        fieldName = postResponseFields{fieldIndex};
        fieldMissing = isnan(double(trials.(fieldName)(:)));
        if ~isequal(fieldMissing, responseMissing)
            error('ds007474:Timing:MissedResponsePattern', ...
                ['Missing values in %s must occur exactly on missed-response ' ...
                 'trials.'], fieldName);
        end
    end

    feedbackDifference = abs(double(trials.tFBOn_Bin(:)) ...
        - double(trials.tFBOn_Mag(:)));
    if any(feedbackDifference(~responseMissing) > tolerance)
        error('ds007474:Timing:FeedbackTimestampMismatch', ...
            'tFBOn_Bin and tFBOn_Mag differ by more than %.3g seconds.', tolerance);
    end

    for trialIndex = 1:numberOfTrials
        runIndex = double(trials.runID(trialIndex));
        if responseMissing(trialIndex)
            orderedTimes = [trials.tStart(trialIndex), ...
                trials.tStim1On(trialIndex), trials.tResp1(trialIndex)];
        else
            orderedTimes = [trials.tStart(trialIndex), ...
                trials.tStim1On(trialIndex), trials.tResp1(trialIndex), ...
                trials.tState2On(trialIndex), ...
                trials.tTerminalState2On(trialIndex), ...
                trials.tFBOn_Bin(trialIndex)];
        end
        if any(diff(double(orderedTimes)) <= 0)
            error('ds007474:Timing:WithinTrialOrder', ...
                'Event timestamps are not strictly increasing on trial %d.', ...
                trials.trialID(trialIndex));
        end
        if any(double(orderedTimes) < runStart(runIndex) - tolerance) ...
                || any(double(orderedTimes) > runEnd(runIndex) + tolerance)
            error('ds007474:Timing:EventOutsideRun', ...
                'Trial %d has an event outside task run %d bounds.', ...
                trials.trialID(trialIndex), runIndex);
        end
    end

    maximumEvents = numberOfTrials * 6;
    participantIDColumn = repmat(canonicalParticipant, maximumEvents, 1);
    sourceSubjectColumn = repmat(string(sprintf('%04d', sourceSubject)), ...
        maximumEvents, 1);
    sourceSessionColumn = repmat(sourceSession, maximumEvents, 1);
    taskRunColumn = nan(maximumEvents, 1);
    behaviorRunColumn = nan(maximumEvents, 1);
    trialIDColumn = nan(maximumEvents, 1);
    trialInRunColumn = nan(maximumEvents, 1);
    eventOrderColumn = nan(maximumEvents, 1);
    eventTypeColumn = strings(maximumEvents, 1);
    onsetColumn = nan(maximumEvents, 1);
    durationColumn = zeros(maximumEvents, 1);
    sourceTimestampColumn = nan(maximumEvents, 1);
    sourceFieldColumn = strings(maximumEvents, 1);
    pairedSourceTimestampColumn = nan(maximumEvents, 1);
    pairedSourceFieldColumn = strings(maximumEvents, 1);
    runStartColumn = nan(maximumEvents, 1);
    runEndColumn = nan(maximumEvents, 1);
    runDurationColumn = nan(maximumEvents, 1);
    responseCodeColumn = nan(maximumEvents, 1);
    responseMissingColumn = false(maximumEvents, 1);
    withinRunBoundsColumn = false(maximumEvents, 1);
    rowCount = 0;

    for trialIndex = 1:numberOfTrials
        append_event(trialIndex, 1, "fixation", "tStart", ...
            double(trials.tStart(trialIndex)), "", NaN);
        append_event(trialIndex, 2, "stimulus", "tStim1On", ...
            double(trials.tStim1On(trialIndex)), "", NaN);

        if responseMissing(trialIndex)
            responseEvent = "response_missing";
        elseif responseCode(trialIndex) == 1
            responseEvent = "response_left";
        else
            responseEvent = "response_right";
        end
        append_event(trialIndex, 3, responseEvent, "tResp1", ...
            double(trials.tResp1(trialIndex)), "", NaN);

        if ~responseMissing(trialIndex)
            append_event(trialIndex, 4, "planet", "tState2On", ...
                double(trials.tState2On(trialIndex)), "", NaN);
            append_event(trialIndex, 5, "pad", "tTerminalState2On", ...
                double(trials.tTerminalState2On(trialIndex)), "", NaN);
            append_event(trialIndex, 6, "outcome", "tFBOn_Bin", ...
                double(trials.tFBOn_Bin(trialIndex)), "tFBOn_Mag", ...
                double(trials.tFBOn_Mag(trialIndex)));
        end
    end

    participantIDColumn = participantIDColumn(1:rowCount);
    sourceSubjectColumn = sourceSubjectColumn(1:rowCount);
    sourceSessionColumn = sourceSessionColumn(1:rowCount);
    taskRunColumn = taskRunColumn(1:rowCount);
    behaviorRunColumn = behaviorRunColumn(1:rowCount);
    trialIDColumn = trialIDColumn(1:rowCount);
    trialInRunColumn = trialInRunColumn(1:rowCount);
    eventOrderColumn = eventOrderColumn(1:rowCount);
    eventTypeColumn = eventTypeColumn(1:rowCount);
    onsetColumn = onsetColumn(1:rowCount);
    durationColumn = durationColumn(1:rowCount);
    sourceTimestampColumn = sourceTimestampColumn(1:rowCount);
    sourceFieldColumn = sourceFieldColumn(1:rowCount);
    pairedSourceTimestampColumn = pairedSourceTimestampColumn(1:rowCount);
    pairedSourceFieldColumn = pairedSourceFieldColumn(1:rowCount);
    runStartColumn = runStartColumn(1:rowCount);
    runEndColumn = runEndColumn(1:rowCount);
    runDurationColumn = runDurationColumn(1:rowCount);
    responseCodeColumn = responseCodeColumn(1:rowCount);
    responseMissingColumn = responseMissingColumn(1:rowCount);
    withinRunBoundsColumn = withinRunBoundsColumn(1:rowCount);

    events = table(participantIDColumn, sourceSubjectColumn, ...
        sourceSessionColumn, taskRunColumn, behaviorRunColumn, trialIDColumn, ...
        trialInRunColumn, eventOrderColumn, eventTypeColumn, onsetColumn, ...
        durationColumn, sourceTimestampColumn, sourceFieldColumn, ...
        pairedSourceTimestampColumn, pairedSourceFieldColumn, runStartColumn, ...
        runEndColumn, runDurationColumn, responseCodeColumn, ...
        responseMissingColumn, withinRunBoundsColumn, ...
        'VariableNames', {'participant_id', 'source_subject_id', ...
        'source_session_id', 'task_run', 'behavior_run_id', 'trial_id', ...
        'trial_in_run', 'event_order', 'event_type', 'onset', 'duration', ...
        'source_timestamp', 'source_field', 'paired_source_timestamp', ...
        'paired_source_field', 'run_start_timestamp', 'run_end_timestamp', ...
        'run_duration', 'response_code', 'response_missing', ...
        'within_run_bounds'});
    events = sortrows(events, {'task_run', 'onset', 'event_order', 'trial_id'});

    if any(~isfinite(events.onset)) || any(~events.within_run_bounds) ...
            || any(events.duration ~= 0)
        error('ds007474:Timing:ExportInvariant', ...
            'Internal export invariant failed before writing the TSV.');
    end

    outputDirectory = fileparts(outputTsv);
    if isempty(outputDirectory)
        outputDirectory = pwd;
        outputTsv = fullfile(outputDirectory, outputTsv);
    elseif exist(outputDirectory, 'dir') ~= 7
        [madeDirectory, message] = mkdir(outputDirectory);
        if ~madeDirectory
            error('ds007474:Timing:OutputDirectory', ...
                'Could not create output directory %s: %s', outputDirectory, message);
        end
    end
    if exist(outputTsv, 'dir') == 7
        error('ds007474:Timing:OutputPath', ...
            'Output path is a directory, not a TSV file: %s', outputTsv);
    end

    temporaryTsv = [tempname(outputDirectory) '.tsv'];
    temporaryCleanup = onCleanup(@() delete_if_present(temporaryTsv));
    writetable(events, temporaryTsv, 'FileType', 'text', ...
        'Delimiter', '\t', 'WriteVariableNames', true);
    [moved, moveMessage] = movefile(temporaryTsv, outputTsv, 'f');
    if ~moved
        error('ds007474:Timing:WriteFailed', ...
            'Could not move completed TSV to %s: %s', outputTsv, moveMessage);
    end
    clear temporaryCleanup;

    validation = struct();
    validation.schema_version = '1.0.0';
    validation.input_mat = inputMat;
    validation.output_tsv = outputTsv;
    validation.participant_id = char(canonicalParticipant);
    validation.source_subject_id = sprintf('%04d', sourceSubject);
    validation.source_session_id = sourceSession;
    validation.number_of_trials = numberOfTrials;
    validation.number_of_runs = numberOfRuns;
    validation.trials_per_run = trialsPerRun';
    validation.number_of_events = height(events);
    validation.missed_response_count = sum(responseMissing);
    validation.missed_response_trial_ids = ...
        double(trials.trialID(responseMissing))';
    validation.t_fix_on_finite_count = sum(isfinite(double(trials.tFixOn)));
    validation.feedback_timestamps_match = true;
    validation.rt_timestamps_match = true;
    validation.all_events_within_run_bounds = all(events.within_run_bounds);
    validation.all_event_durations_zero = all(events.duration == 0);
    validation.minimum_onset = min(events.onset);
    validation.maximum_onset = max(events.onset);
    validation.event_counts = event_count_struct(events.event_type);
    validation.run_summary = repmat(struct('task_run', [], ...
        'behavior_run_id', [], 'trial_count', [], 'event_count', [], ...
        'run_start_timestamp', [], 'run_end_timestamp', [], ...
        'run_duration', [], 'minimum_onset', [], 'maximum_onset', []), ...
        numberOfRuns, 1);
    for runIndex = 1:numberOfRuns
        runEvents = events.task_run == runIndex;
        validation.run_summary(runIndex).task_run = runIndex;
        validation.run_summary(runIndex).behavior_run_id = ...
            runIndex + options.BehaviorRunOffset;
        validation.run_summary(runIndex).trial_count = trialsPerRun(runIndex);
        validation.run_summary(runIndex).event_count = sum(runEvents);
        validation.run_summary(runIndex).run_start_timestamp = runStart(runIndex);
        validation.run_summary(runIndex).run_end_timestamp = runEnd(runIndex);
        validation.run_summary(runIndex).run_duration = runDuration(runIndex);
        validation.run_summary(runIndex).minimum_onset = min(events.onset(runEvents));
        validation.run_summary(runIndex).maximum_onset = max(events.onset(runEvents));
    end
    validation.assumptions = struct();
    validation.assumptions.canonical_participant_id = ...
        'sub-MBMF + four-digit source subject + two-digit source session';
    validation.assumptions.behavior_run_mapping = sprintf( ...
        'behavior_run_id = task_run + %d', options.BehaviorRunOffset);
    validation.assumptions.fixation_mapping = ...
        'fixation uses tStart because the task writes the fixation flip there';
    validation.assumptions.feedback_mapping = ...
        'one outcome event uses tFBOn_Bin after equality check with tFBOn_Mag';
    validation.assumptions.missed_response_mapping = ...
        ['retain fixation, stimulus, and response_missing; omit unavailable ' ...
         'planet, pad, and outcome events'];
    validation.assumptions.duration_mapping = ...
        'all exported task events are zero-duration stick functions';

    function append_event(trialIndex, eventOrder, eventType, sourceField, ...
            sourceTimestamp, pairedSourceField, pairedSourceTimestamp)
        rowCount = rowCount + 1;
        eventRun = double(trials.runID(trialIndex));
        onset = sourceTimestamp - runStart(eventRun);
        inBounds = onset >= -tolerance ...
            && onset <= runDuration(eventRun) + tolerance;

        taskRunColumn(rowCount) = eventRun;
        behaviorRunColumn(rowCount) = eventRun + options.BehaviorRunOffset;
        trialIDColumn(rowCount) = double(trials.trialID(trialIndex));
        trialInRunColumn(rowCount) = trialInRun(trialIndex);
        eventOrderColumn(rowCount) = eventOrder;
        eventTypeColumn(rowCount) = eventType;
        onsetColumn(rowCount) = onset;
        sourceTimestampColumn(rowCount) = sourceTimestamp;
        sourceFieldColumn(rowCount) = sourceField;
        pairedSourceTimestampColumn(rowCount) = pairedSourceTimestamp;
        pairedSourceFieldColumn(rowCount) = pairedSourceField;
        runStartColumn(rowCount) = runStart(eventRun);
        runEndColumn(rowCount) = runEnd(eventRun);
        runDurationColumn(rowCount) = runDuration(eventRun);
        responseCodeColumn(rowCount) = responseCode(trialIndex);
        responseMissingColumn(rowCount) = responseMissing(trialIndex);
        withinRunBoundsColumn(rowCount) = inBounds;
    end
end


function require_fields(value, requiredFields, label)
    missingFields = requiredFields(~isfield(value, requiredFields));
    if ~isempty(missingFields)
        error('ds007474:Timing:MissingFields', ...
            '%s is missing fields: %s', label, strjoin(missingFields, ', '));
    end
end


function id = integer_id(value, label)
    if isnumeric(value)
        if ~isscalar(value)
            error('ds007474:Timing:InvalidID', '%s must be scalar.', label);
        end
        id = double(value);
    else
        text = strtrim(char(string(value)));
        id = str2double(text);
    end
    if ~isscalar(id) || ~isfinite(id) || id < 0 || id ~= round(id)
        error('ds007474:Timing:InvalidID', ...
            '%s must identify one nonnegative integer.', label);
    end
end


function assert_equal_id(actual, expected, actualLabel, expectedLabel)
    if actual ~= expected
        error('ds007474:Timing:SourceIdentityMismatch', ...
            '%s is %d but %s is %d.', ...
            actualLabel, actual, expectedLabel, expected);
    end
end


function tokens = parse_source_filename(fileName)
    [~, baseName, ~] = fileparts(strtrim(fileName));
    match = regexp(baseName, ...
        '^subID_(\d+)_sesID_(\d+)_MBMF_fMRI(?:_.*)?$', 'tokens', 'once');
    if isempty(match)
        error('ds007474:Timing:SourceFilename', ...
            'Could not parse source subject and session from %s.', fileName);
    end
    tokens = struct();
    tokens.subject = str2double(match{1});
    tokens.session = str2double(match{2});
end


function counts = event_count_struct(eventTypes)
    labels = unique(eventTypes, 'stable');
    counts = struct();
    for labelIndex = 1:numel(labels)
        fieldName = matlab.lang.makeValidName(char(labels(labelIndex)));
        counts.(fieldName) = sum(eventTypes == labels(labelIndex));
    end
end


function delete_if_present(pathName)
    if exist(pathName, 'file') == 2
        delete(pathName);
    end
end
