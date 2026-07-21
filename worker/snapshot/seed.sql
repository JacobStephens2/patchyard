DROP TABLE IF EXISTS etaFactoryParitySeed;
CREATE TABLE etaFactoryParitySeed (
  id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  marker VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
INSERT INTO etaFactoryParitySeed (id, marker)
VALUES (1, 'redacted-snapshot-row');
