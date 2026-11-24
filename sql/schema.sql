CREATE DATABASE IF NOT EXISTS neurodb CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE neurodb;
CREATE TABLE IF NOT EXISTS studies (
 study_id INT PRIMARY KEY, accession VARCHAR(32) NOT NULL UNIQUE,
 title VARCHAR(255) NOT NULL, doi VARCHAR(128), snapshot VARCHAR(100) NOT NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS source_files (
 source_file_id INT AUTO_INCREMENT PRIMARY KEY, local_path VARCHAR(400) NOT NULL,
 source_url VARCHAR(1000) NOT NULL, snapshot VARCHAR(255) NOT NULL,
 checksum CHAR(64) NOT NULL, license_status VARCHAR(255) NOT NULL, available_on_disk BOOLEAN NOT NULL DEFAULT 1,
 UNIQUE KEY source_identity(local_path,checksum)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS ingestion_runs (
 ingestion_id BIGINT AUTO_INCREMENT PRIMARY KEY, transform_version VARCHAR(80) NOT NULL,
 code_checksum CHAR(64) NOT NULL, executed_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
 status ENUM('running','passed','failed') NOT NULL, message TEXT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS ingestion_records (
 ingestion_id BIGINT NOT NULL, source_file_id INT NOT NULL, rows_loaded INT NOT NULL,
 validation_status VARCHAR(40) NOT NULL, message TEXT,
 PRIMARY KEY(ingestion_id,source_file_id),
 FOREIGN KEY(ingestion_id) REFERENCES ingestion_runs(ingestion_id),
 FOREIGN KEY(source_file_id) REFERENCES source_files(source_file_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS participants (
 participant_id INT AUTO_INCREMENT PRIMARY KEY, study_id INT NOT NULL,
 source_person_id CHAR(4) NOT NULL, bids_label VARCHAR(32) NOT NULL, task_order TINYINT NOT NULL,
 design_variant VARCHAR(40) NOT NULL, inclusion_status VARCHAR(40) NOT NULL,
 analytic_inclusion_status VARCHAR(40) NOT NULL DEFAULT 'unknown', exclusion_reason TEXT,
 metadata_note TEXT, source_file_id INT NOT NULL,
 UNIQUE KEY participant_identity(study_id,bids_label),
 FOREIGN KEY(study_id) REFERENCES studies(study_id),
 FOREIGN KEY(source_file_id) REFERENCES source_files(source_file_id),
 CHECK(task_order IN (1,2))
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS sessions (
 session_id INT AUTO_INCREMENT PRIMARY KEY, participant_id INT NOT NULL,
 session_label VARCHAR(40) NOT NULL, UNIQUE KEY session_identity(participant_id,session_label),
 FOREIGN KEY(participant_id) REFERENCES participants(participant_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS runs (
 run_id INT AUTO_INCREMENT PRIMARY KEY, session_id INT NOT NULL,
 run_type ENUM('structural','functional') NOT NULL, run_number SMALLINT NOT NULL,
 behavior_run_number SMALLINT NOT NULL, source_run_label VARCHAR(40) NOT NULL,
 repetition_time DOUBLE, scan_count INT, run_duration DOUBLE, source_file_id INT NOT NULL,
 UNIQUE KEY run_identity(session_id,run_type,run_number),
 FOREIGN KEY(session_id) REFERENCES sessions(session_id),
 FOREIGN KEY(source_file_id) REFERENCES source_files(source_file_id),
 CHECK(run_number>0), CHECK(repetition_time IS NULL OR repetition_time>0),
 CHECK(scan_count IS NULL OR scan_count>0)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS trials (
 trial_id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id INT NOT NULL,
 trial_number INT NOT NULL, source_trial_number INT NOT NULL, source_row_number INT NOT NULL,
 response_valid BOOLEAN NOT NULL, source_file_id INT NOT NULL,
 UNIQUE KEY trial_identity(run_id,trial_number), UNIQUE KEY run_trial_identity(run_id,trial_id),
 FOREIGN KEY(run_id) REFERENCES runs(run_id),
 FOREIGN KEY(source_file_id) REFERENCES source_files(source_file_id),
 CHECK(trial_number>0), CHECK(response_valid IN (0,1))
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS two_step_trial_details (
 trial_id BIGINT PRIMARY KEY, chosen_ship TINYINT, visited_planet TINYINT, visited_pad TINYINT,
 reward TINYINT, reward_magnitude DOUBLE, transition_type ENUM('common','rare'),
 reward_condition TINYINT, contingency_condition TINYINT, state_condition TINYINT,
 response_time DOUBLE,
 FOREIGN KEY(trial_id) REFERENCES trials(trial_id),
 CHECK(chosen_ship IN (1,2)), CHECK(visited_planet IN (1,2)),
 CHECK(visited_pad BETWEEN 1 AND 4), CHECK(reward IN (0,1)),
 CHECK(response_time IS NULL OR response_time>=0)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS event_types (
 event_type_id INT PRIMARY KEY, event_name VARCHAR(40) NOT NULL UNIQUE, trial_status_rules VARCHAR(255) NOT NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS events (
 event_id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id INT NOT NULL, trial_id BIGINT,
 event_type_id INT NOT NULL, event_sequence SMALLINT NOT NULL,
 onset_seconds DOUBLE NOT NULL, duration_seconds DOUBLE NOT NULL,
 source_timestamp DOUBLE NOT NULL, source_field VARCHAR(40) NOT NULL, source_file_id INT NOT NULL,
 trial_scope BIGINT GENERATED ALWAYS AS (COALESCE(trial_id,0)) STORED,
 UNIQUE KEY event_identity(run_id,trial_scope,event_type_id,event_sequence),
 KEY events_trial_fk(run_id,trial_id), KEY idx_events_run_onset(run_id,onset_seconds),
 FOREIGN KEY(run_id) REFERENCES runs(run_id),
 FOREIGN KEY(run_id,trial_id) REFERENCES trials(run_id,trial_id),
 FOREIGN KEY(event_type_id) REFERENCES event_types(event_type_id),
 FOREIGN KEY(source_file_id) REFERENCES source_files(source_file_id),
 CHECK(onset_seconds>=-0.000001), CHECK(duration_seconds>=0), CHECK(event_sequence>0)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS participant_measures (
 participant_id INT NOT NULL, measure_name VARCHAR(80) NOT NULL, method_version VARCHAR(80) NOT NULL,
 value DOUBLE NOT NULL, source_file_id INT NOT NULL,
 PRIMARY KEY(participant_id,measure_name,method_version),
 FOREIGN KEY(participant_id) REFERENCES participants(participant_id),
 FOREIGN KEY(source_file_id) REFERENCES source_files(source_file_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS model_specifications (
 model_id INT PRIMARY KEY, model_name VARCHAR(128) NOT NULL, version VARCHAR(100) NOT NULL,
 code_reference VARCHAR(512) NOT NULL, UNIQUE KEY model_identity(model_name,version)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS fitting_jobs (
 job_id INT PRIMARY KEY, model_id INT NOT NULL, fitting_method VARCHAR(128) NOT NULL,
 prior_spec JSON, code_version VARCHAR(100) NOT NULL, run_status VARCHAR(80) NOT NULL,
 FOREIGN KEY(model_id) REFERENCES model_specifications(model_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS participant_fits (
 fit_id INT AUTO_INCREMENT PRIMARY KEY, job_id INT NOT NULL, participant_id INT NOT NULL,
 objective_value DOUBLE, objective_kind VARCHAR(80) NOT NULL, fit_status VARCHAR(80) NOT NULL,
 source_file_id INT NOT NULL, UNIQUE KEY fit_identity(job_id,participant_id),
 FOREIGN KEY(job_id) REFERENCES fitting_jobs(job_id),
 FOREIGN KEY(participant_id) REFERENCES participants(participant_id),
 FOREIGN KEY(source_file_id) REFERENCES source_files(source_file_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS parameter_definitions (
 model_id INT NOT NULL, parameter_name VARCHAR(80) NOT NULL, transform VARCHAR(100) NOT NULL,
 lower_bound DOUBLE, upper_bound DOUBLE, applicability VARCHAR(255),
 PRIMARY KEY(model_id,parameter_name), FOREIGN KEY(model_id) REFERENCES model_specifications(model_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS parameter_estimates (
 fit_id INT NOT NULL, parameter_name VARCHAR(80) NOT NULL, raw_value DOUBLE NOT NULL, applied_value DOUBLE NOT NULL,
 PRIMARY KEY(fit_id,parameter_name), FOREIGN KEY(fit_id) REFERENCES participant_fits(fit_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS variable_definitions (
 variable_id INT PRIMARY KEY, model_id INT NOT NULL, variable_name VARCHAR(80) NOT NULL,
 stage VARCHAR(40) NOT NULL, locking_event_type_id INT, units VARCHAR(100) NOT NULL,
 UNIQUE KEY variable_identity(model_id,variable_name),
 FOREIGN KEY(model_id) REFERENCES model_specifications(model_id),
 FOREIGN KEY(locking_event_type_id) REFERENCES event_types(event_type_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS latent_values (
 fit_id INT NOT NULL, trial_id BIGINT NOT NULL, variable_id INT NOT NULL, value DOUBLE NOT NULL,
 PRIMARY KEY(fit_id,trial_id,variable_id), FOREIGN KEY(fit_id) REFERENCES participant_fits(fit_id),
 FOREIGN KEY(trial_id) REFERENCES trials(trial_id),
 FOREIGN KEY(variable_id) REFERENCES variable_definitions(variable_id)
) ENGINE=InnoDB;
CREATE OR REPLACE VIEW trial_context AS
 SELECT p.participant_id,p.bids_label,p.design_variant,p.task_order,p.analytic_inclusion_status,
 r.run_id,r.run_type,r.run_number,r.behavior_run_number,t.trial_id,t.trial_number,
 t.source_trial_number,t.source_row_number,t.response_valid,t.source_file_id,
 d.chosen_ship,d.visited_planet,d.visited_pad,d.reward,d.reward_magnitude,d.transition_type,
 d.reward_condition,d.contingency_condition,d.state_condition,d.response_time
 FROM participants p JOIN sessions s USING(participant_id) JOIN runs r USING(session_id)
 JOIN trials t USING(run_id) JOIN two_step_trial_details d USING(trial_id);
