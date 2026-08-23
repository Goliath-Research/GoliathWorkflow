SELECT 
  b.Name, 
  count(*) AS BatchSize 
FROM 
  portal.LabSamples ls 
    inner JOIN portal.Batches b ON ls.BatchID = b.ID
    inner JOIN portal.Samples s ON s.ID = ls.SampleID
GROUP BY b.Name;

SELECT 
  ls.ID,
  ls.SampleID,
  ls.Sample,
  b.Name AS Batch,
  d.Name AS Disease
FROM 
  portal.LabSamples ls 
    inner JOIN portal.Batches b ON ls.BatchID = b.ID
    inner JOIN portal.Samples s ON s.ID = ls.SampleID
    inner JOIN portal.Diseases d ON s.DiseaseID = d.ID
WHERE 
  b.Name = '26418'-- AND 
  ls.Sample LIKE '017224%' OR
  ls.Sample LIKE '017500%' OR
  ls.Sample LIKE '013243%';

SELECT * FROM portal.LabSamples WHERE id BETWEEN 207 and 209;

SELECT * FROM portal.Batches;

SELECT * FROM portal.Samples WHERE ParticipantID LIKE '017224%';
SELECT * FROM portal.Patients WHERE Name LIKE '017500%';
SELECT * FROM portal.GroupSamples WHERE SampleID BETWEEN 207 AND 209;

SELECT
  d.Name AS Disease,
  b.Name AS Batch,
  count(*) AS Qty
FROM
  portal.Samples s
    INNER JOIN portal.LabSamples ls ON s.ID = ls.SampleID
    INNER JOIN portal.Batches b ON ls.BatchID = b.ID
    INNER JOIN portal.Diseases d ON s.DiseaseID = d.ID
GROUP BY d.Name, b.Name;

SELECT * FROM portal.Groups;
SELECT 
  grp.Name,
  grp.ID,
  avg(spc.PSA) as AvgPSA,
  count(*) AS Qty
 FROM
  portal.Groups grp 
    --INNER JOIN portal.GroupSamples gs ON grp.ID = gs.GroupID
    INNER JOIN portal.SamplesProstateCancer spc ON grp.ID = COALESCE(CAST(spc.GleasonScore AS INT), 0) + 1
GROUP BY
  grp.Name,
  grp.ID;

INSERT INTO portal.GroupSamples(GroupID, SampleID)
  SELECT
    COALESCE(CAST(spc.GleasonScore AS INT), 0) + 1 AS GroupID,
    spc.ID
  FROM portal.SamplesProstateCancer spc;

select count(*) FROM portal.GroupSamples;
TRUNCATE TABLE portal.GroupSamples;

SELECT * 
FROM portal.LabSamples 
WHERE 
  Sample LIKE '013243_10%' OR -- 013243_10C21.12
  Sample LIKE '017224%' OR -- 017224_10_K20_1
  Sample LIKE '017500%' OR -- 017500_10M_15_56
  Sample LIKE 'DBCST-071%' -- DBCST-071125-111805;  

UPDATE portal.Samples
SET
  DiseaseID = 1
WHERE PatientID IN (SELECT ID FROM portal.SamplesProstateCancer);
