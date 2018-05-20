-- Create schema
CREATE SCHEMA cohd;


-- Create tables
CREATE TABLE IF NOT EXISTS cohd.concept (
  concept_id INT(11) NOT NULL,
  concept_name VARCHAR(255) NOT NULL,
  domain_id VARCHAR(20) NOT NULL,
  concept_class_id VARCHAR(20) NOT NULL);

CREATE TABLE cohd.concept_counts (
  concept_id INT(11) UNIQUE NOT NULL,
  concept_count INT UNSIGNED NOT NULL,
  concept_frequency DOUBLE NOT NULL);

CREATE TABLE cohd.concept_pair_counts (
  concept_id_1 INT(11) NOT NULL,
  concept_id_2 INT(11) NOT NULL,
  concept_count INT UNSIGNED NOT NULL,
  concept_frequency DOUBLE NOT NULL);



-- Load data  
TRUNCATE cohd.concept;
LOAD DATA LOCAL INFILE 'D:/cohd/translator_concept_count_data/cohd_data_cleaned/concepts.txt' 
INTO TABLE cohd.concept
FIELDS TERMINATED BY '\t' ENCLOSED BY '"' ESCAPED BY '\\'
LINES TERMINATED BY '\n' STARTING BY ''
IGNORE 0 LINES;

TRUNCATE cohd.concept_counts;
LOAD DATA LOCAL INFILE 'D:/cohd/translator_concept_count_data/cohd_data_cleaned/concept_counts.txt' 
INTO TABLE cohd.concept_counts
FIELDS TERMINATED BY '\t' ENCLOSED BY '' ESCAPED BY '\\'
LINES TERMINATED BY '\n' STARTING BY ''
IGNORE 0 LINES;

TRUNCATE cohd.concept_pair_counts;
LOAD DATA LOCAL INFILE 'D:/cohd/translator_concept_count_data/cohd_data_cleaned/concept_pair_counts.txt' 
INTO TABLE cohd.concept_pair_counts
FIELDS TERMINATED BY '\t' ENCLOSED BY '' ESCAPED BY '\\'
LINES TERMINATED BY '\n' STARTING BY ''
IGNORE 0 LINES;


-- Add indices
ALTER TABLE cohd.concept 
ADD PRIMARY KEY (concept_id),
ADD INDEX concept_class (concept_class_id ASC),
ADD INDEX domain (domain_id ASC);

ALTER TABLE cohd.concept_counts
ADD PRIMARY KEY (concept_id);
ALTER TABLE cohd.concept_counts
ADD CONSTRAINT concept_id
  FOREIGN KEY (concept_id)
  REFERENCES cohd.concept (concept_id)
  ON DELETE NO ACTION
  ON UPDATE NO ACTION;
  
ALTER TABLE cohd.concept_pair_counts
ADD PRIMARY KEY (concept_id_1, concept_id_2),
ADD INDEX concept_id_2_idx (concept_id_2 ASC);
ALTER TABLE cohd.concept_pair_counts
ADD CONSTRAINT concept_id_1
  FOREIGN KEY (concept_id_1)
  REFERENCES cohd.concept (concept_id)
  ON DELETE NO ACTION
  ON UPDATE NO ACTION,
ADD CONSTRAINT concept_id_2
  FOREIGN KEY (concept_id_2)
  REFERENCES cohd.concept (concept_id)
  ON DELETE NO ACTION
  ON UPDATE NO ACTION;

