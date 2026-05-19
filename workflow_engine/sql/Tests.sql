SELECT
  sample
FROM PCaH
WHERE sample NOT IN (SELECT Name FROM portal.Patients);

SELECT * FROM PCd WHERE Status = 'Healthy' AND Source = 'KUMC' AND [Psomagen ID] LIKE '5929%';

SELECT count(*) FROM PCd WHERE [Psomagen ID] NOT IN (SELECT Name FROM portal.Patients);

SELECT
  DiseaseID,
  count(*) AS Qty
FROM portal.Samples
GROUP BY DiseaseID;
