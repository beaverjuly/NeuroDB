function export_cohort(root)
% Cohort wrapper around the strict pilot exporter, preserving failed audits.
    batch=jsondecode(fileread(fullfile(root,'data','derived','batch.json')));
    status=repmat(struct('bids_label','','passed',false,'reason',''),numel(batch),1);
    for i=1:numel(batch)
        item=batch(i);
        status(i).bids_label=item.label;
        try
            addpath(fullfile(root,'scripts','events'));
            run_pilot_timing_export(item.config,item.output);
            status(i).passed=true;
        catch err
            status(i).reason=[err.identifier ' | ' err.message];
            fprintf('EXCLUDED %s %s\n',item.label,status(i).reason);
        end
        fid=fopen(fullfile(root,'data','derived','cohort_validation.json'),'w');
        fwrite(fid,jsonencode(status),'char');fclose(fid);
    end
    fprintf('Validated %d of %d participants\n',sum([status.passed]),numel(status));
end
