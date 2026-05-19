SELECT * FROM portal.Institutions;
SELECT * FROM portal.Labs;
SELECT * FROM portal.Groups;
SELECT * from portal.Diseases;
SELECT * from portal.Patients;
SELECT * FROM portal.Samples;
SELECT * FROM portal.SamplesProstateCancer;
SELECT * from portal.GroupSamples;
SELECT * FROM portal.LabSamples;

-- Adding Breast Cancer to the database
-- 1) Patients were already imported (PatientID = PsomagenID)
-- 2) Samples come from bc2 (197)
INSERT INTO portal.Samples(PatientID, Age, BMI, DiseaseID, Stage)
  SELECT
    p.ID,
    Age,
    BMI,
    2 AS DiseaseID, -- breast
    Stage
  FROM bc2 b inner JOIN portal.Patients p ON b.PatientID = p.Name;
-- 3) Add breast cancer information to portal.SamplesBreastCancer
INSERT INTO portal.SamplesBreastCancer(ID, ER_Status, PR_Status, HER2_Status)
  SELECT
    s.ID,
    (CASE b.ER_Status WHEN 'Positive' THEN 1 ELSE 0 END) AS ER_Status,
    (CASE b.PR_Status WHEN 'Positive' THEN 1 ELSE 0 END) AS PR_Status,
    (CASE b.HER2_Status WHEN 'Positive' THEN 1 ELSE 0 END) AS HER2_Status
  FROM
    portal.Samples s
      INNER JOIN portal.Patients p ON s.PatientID = p.ID
      INNER JOIN bc2 b ON p.Name = b.PatientID;
-- 4) Add breast cancer samples to GroupSamples
INSERT INTO portal.GroupSamples(GroupID, SampleID)
  SELECT
    2 AS GroupID,
    ID as SampleID
  FROM portal.Samples
  WHERE DiseaseID = 2;
-- 5) Add breast cancer samples to LabSamples
INSERT INTO portal.LabSamples(SampleID, LabID, Batch, Sample)
  SELECT
    s.ID,
    1 AS LabID, -- psomagen
    '26454' AS Batch,
    p.Name
  FROM portal.Samples s INNER JOIN portal.Patients p ON s.PatientID = p.ID
  WHERE DiseaseID = 2;

----
-- 240 Prostate Cancer samples
-- 197 Breast Cancer samples
----
-- select count(*) FROM portal.Samples; -- 437
-- SELECT count(*) FROM portal.Patients; -- 785
SELECT cancer_type, count(*) FROM dbo.all_batches GROUP BY cancer_type;
SELECT Batch, count(*) FROM dbo.all_batches GROUP BY Batch;
SELECT * FROM all_batches WHERE Sample LIKE 'DB%' OR Sample LIKE 'HB%';
SELECT * FROM all_batches WHERE Batch = 'male_colorectal';
SELECT Batch, count(*) FROM all_batches WHERE cancer_type = 'prostate' GROUP BY Batch;
SELECT count(*) FROM dbo.[26454];
SELECT count(*) FROM dbo.[26454] b inner JOIN portal.Patients p ON b.PsomagenID = p.Name;
WITH BreastSamples AS
(
  SELECT
    p.Name AS Sample
  FROM
    portal.Patients p
      INNER JOIN portal.Samples s ON p.ID = s.PatientID
  WHERE s.DiseaseID = 2
)
SELECT * 
FROM all_batches 
WHERE PatientID NOT IN (SELECT Sample FROM BreastSamples) AND cancer_type = 'breast';

select count(*) FROM portal.Samples s inner JOIN portal.LabSamples ls ON s.ID = ls.SampleID group BY DiseaseID;
SELECT Batch, count(*) FROM portal.LabSamples GROUP BY Batch;
select count(*) FROM dbo.[26368] b inner JOIN portal.LabSamples ls ON b.PsomagenID = ls.Sample;

--UPDATE all_batches
--SET
--  cancer_type = NULL
--WHERE cancer_type = 'prostate' AND Batch = 'healthy_controls' AND Sex = 'F';
WITH ProstateSamples AS
(
  SELECT
    p.Name AS Sample
  FROM
    portal.Patients p
      INNER JOIN portal.Samples s ON p.ID = s.PatientID
  WHERE s.DiseaseID = 1
)
SELECT * 
FROM all_batches 
WHERE PatientID NOT IN (SELECT Sample FROM ProstateSamples) AND cancer_type = 'prostate';

DELETE FROM all_batches WHERE SampleType = 'Plasma';

SELECT count(*) FROM dbo.all_batches;
UPDATE dbo.pancreatic
SET
  [Psomagen ID] = TRIM([Psomagen ID]),
  Participant_Gender = (CASE Participant_Gender WHEN 'Female Gender' THEN 'F' ELSE 'M' END);

SELECT * FROM dbo.all_batches WHERE cancer_type LIKE 'pancreatic' AND Sample NOT IN (SELECT [Psomagen ID] FROM pancreatic);

-- We need to add 30 samples from batch 25862 (15 + 15) and 54 healthy controls (5929-XXXXXX)
-- Total healthy controls should be 69
-- There are 15 more breast cancer samples

--delete from portal.Samples;

-- Precise scale for Gleason Score
UPDATE dbo.PCd
SET GS = CASE 
    WHEN Gleason LIKE '3+3%' THEN 1
    WHEN Gleason LIKE '3+4%' THEN 2
    WHEN Gleason LIKE '4+3%' THEN 3
    WHEN Gleason LIKE '4+4%' THEN 4
    WHEN Gleason LIKE '4+5%' THEN 5
    WHEN Gleason LIKE '5+4%' THEN 6
    WHEN Gleason LIKE '5+5%' THEN 7
    ELSE NULL
END;

-- Additional information for Prostate Cancer samples
INSERT INTO portal.SamplesProstateCancer(ID, PSA, GleasonScore)
  SELECT
    s.ID,
    d.PSA,
    d.GS
  FROM 
    portal.Samples s 
      INNER JOIN portal.Patients p ON s.PatientID = p.ID
      INNER JOIN PCd d ON p.Name = d.[Psomagen ID];


INSERT INTO portal.Samples(PatientID, Age, BMI, DiseaseID, Stage)
  SELECT * 
  FROM viewNewPCaSamples
  WHERE PatientID NOT IN (SELECT PatientID FROM portal.Samples);
SELECT Name, count(*) AS Qty from portal.Patients GROUP BY Name HAVING count(*) > 1;
select distinct(Sample) FROM all_batches WHERE Sample is not null;

SELECT * from bc2;
SELECT Stage, count(*) as Qty FROM bc2 GROUP BY Stage;
select count(*) FROM bc2 inner JOIN portal.Patients p ON bc2.PatientID = p.Name;

DELETE FROM bc2 WHERE len(PatientID) < 2;
--insert into portal.Diseases(Name)
--  SELECT cancer_type, count(*) as Qty FROM dbo.all_batches GROUP BY cancer_type ORDER BY count(*) desc;
--SELECT * FROM Labs;
--INSERT INTO portal.Labs(Name)
--  SELECT Name FROM dbo.Labs ORDER BY ID;
--INSERT INTO portal.Groups(Name, Description)
--  VALUES
--    ('PCaH', 'Prostate Cancer Healthy'),
--    ('PCa1', 'Prostate Cancer Gleason Score 3+3'),
--    ('PCa2', 'Prostate Cancer Gleason Score 3+4'),
--    ('PCa3', 'Prostate Cancer Gleason Score 4+3'),
--    ('PCA4', 'Prostate Cancer Gleason Score >= 4+4');
--delete FROM portal.Patients;
--INSERT INTO portal.Patients(InstitutionID, Name, Sex, Race, Ethnicity)
--  SELECT
--    1 AS InstitutionID,
--    Sample as Name,
--    Sex,
--    Race,
--    Ethnicity
--  FROM dbo.all_batches;
SELECT * FROM portal.Samples;
--INSERT INTO portal.Patients(InstitutionID, Name, Sex, Race, Ethnicity)
--  SELECT 
--    1 AS InstitutionID,
--    [Psomagen ID] AS Name, 
--    'M' AS Sex, 
--    Race, 
--    Ethnicity 
--  FROM PCd 
--  WHERE [Psomagen ID] NOT IN (SELECT Name FROM portal.Patients);

--  SELECT
--    1 AS InstitutionID,
--    PatientID as Name,
--    'F' AS Sex,
--    Race,
--    Ethnicity
--  FROM dbo.breast_cancer;
SELECT * FROM PCaH;
SELECT * FROM PCa1;
SELECT * FROM PCa2;
SELECT * from PCa3;
SELECT * FROM PCa4;
SELECT * from portal.Patients WHERE len(Name) < 3;
SELECT * FROM all_batches WHERE cancer_type = 'breast';
--select DISTINCT cancer_type FROM all_batches;
SELECT * from breast_cancer;
SELECT count(*) as Qty FROM all_batches ab inner JOIN breast_cancer bc ON ab.Sample = bc.PatientID;

INSERT INTO portal.LabSamples(SampleID, LabID, Batch, Sample)
  SELECT * FROM viewLabSamplesProstate;

INSERT into portal.GroupSamples(GroupID, SampleID)
  SELECT
    COALESCE(CAST(Stage AS INT), 0) + 1 AS GroupID,
    ID
  FROM portal.Samples;

SELECT DISTINCT Sample FROM all_batches WHERE cancer_type = 'prostate';
SELECT * FROM viewPCaH;
SELECT
  Groups.ID AS GroupID
 ,Samples.ID AS SampleID
FROM portal.Groups
    ,PCaH
     INNER JOIN portal.Samples
       ON PCaH.sample = Samples.PatientID;
SELECT * FROM PCaH h inner JOIN portal.Patients p ON h.sample = p.Name;
SELECT * FROM portal.Samples;

UPDATE portal.LabSamples
SET
  BatchID = (SELECT ID FROM dbo.Batches WHERE Name = Batch);

SELECT * FROM portal.LabSamples;
SELECT BatchID, count(*) FROM portal.LabSamples group BY BatchID;

UPDATE portal.LabSamples
SET
  BatchID = 7
WHERE BatchID is null;

ALTER SCHEMA portal TRANSFER dbo.vInstitutions;

SELECT GleasonScore, count(*) FROM portal.SamplesProstateCancer GROUP BY GleasonScore;

SELECT
  grp.Name AS [Group],
  --ls.Sample,
  count(*) AS GroupSize
FROM
  portal.Groups grp
    inner JOIN portal.GroupSamples gs ON grp.ID = gs.GroupID
    INNER JOIN portal.LabSamples ls ON gs.SampleID = ls.SampleID
    INNER JOIN portal.SamplesProstateCancer spc ON spc.ID = ls.ID
GROUP BY
  grp.Name
  --,ls.Sample;

SELECT
  ls.Sample
FROM
  portal.Groups grp
    inner JOIN portal.GroupSamples gs ON grp.ID = gs.GroupID
    INNER JOIN portal.LabSamples ls ON gs.SampleID = ls.SampleID
    INNER JOIN portal.SamplesProstateCancer spc ON spc.ID = ls.ID
WHERE
  grp.Name = 'PCaH';

