-- Origen "on-premise" del laboratorio (Anexo A). Ejecutar en BDOrigen del
-- SQL Server local, NO en Azure SQL. Datos ficticios reservados para pruebas.
CREATE TABLE dbo.DeudaOrigen (
 PapeletaId varchar(30) PRIMARY KEY,
 TipoDoc varchar(3) NOT NULL CHECK (TipoDoc IN ('DNI','RUC')),
 Documento varchar(11) NOT NULL,
 Placa varchar(10) NULL,
 ImporteOriginal decimal(18,2) NOT NULL CHECK (ImporteOriginal >= 0),
 Activa bit NOT NULL,
 FechaModificacion datetime2 NOT NULL
);
INSERT dbo.DeudaOrigen VALUES
('P0001','DNI','00000001','ABC123',100.00,1,SYSUTCDATETIME()),
('P0002','RUC','20000000001','XYZ789',250.00,1,SYSUTCDATETIME()),
('P0003','DNI','00000002','DEF456',80.00,1,SYSUTCDATETIME());
GO
-- Extracción controlada que lee ADF: conteo, corte y filas de la misma
-- fotografía (8.4 y "Mapeo de Copy"). Se lee con aislamiento SNAPSHOT.
CREATE OR ALTER VIEW dbo.vDeudaExportable AS
SELECT PapeletaId,TipoDoc,Documento,Placa,ImporteOriginal,Activa
FROM dbo.DeudaOrigen;
GO
