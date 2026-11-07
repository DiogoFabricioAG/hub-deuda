-- Extracción consistente para ADF ("Mapeo de Copy" y 8.7): conteo, corte y
-- filas se toman de la misma fotografía, en una sola transacción. ADF lee
-- solo la exportación identificada por ExportId; el lector no ve la tabla
-- operativa.
CREATE TABLE dbo.ExportControl (
 ExportId uniqueidentifier PRIMARY KEY,
 CorteUtc datetime2 NOT NULL,
 Filas int NOT NULL,
 CreadoUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE TABLE dbo.DeudaExport (
 ExportId uniqueidentifier NOT NULL REFERENCES dbo.ExportControl(ExportId),
 PapeletaId varchar(30) NOT NULL,
 TipoDoc varchar(3) NOT NULL,
 Documento varchar(11) NOT NULL,
 Placa varchar(10) NULL,
 ImporteOriginal decimal(18,2) NOT NULL,
 Activa bit NOT NULL,
 PRIMARY KEY (ExportId,PapeletaId)
);
GO
CREATE OR ALTER PROCEDURE dbo.usp_CrearExportacion
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 DECLARE @id uniqueidentifier=NEWID(),@corte datetime2=SYSUTCDATETIME(),@n int;
 SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
 BEGIN TRAN;
  INSERT dbo.ExportControl (ExportId,CorteUtc,Filas) VALUES (@id,@corte,0);
  INSERT dbo.DeudaExport (ExportId,PapeletaId,TipoDoc,Documento,Placa,ImporteOriginal,Activa)
  SELECT @id,PapeletaId,TipoDoc,Documento,Placa,ImporteOriginal,Activa
  FROM dbo.vDeudaExportable;
  SET @n=@@ROWCOUNT;
  UPDATE dbo.ExportControl SET Filas=@n WHERE ExportId=@id;
 COMMIT;
 -- Retención corta: las exportaciones solo sirven a la copia en curso.
 DELETE e FROM dbo.DeudaExport e JOIN dbo.ExportControl c ON c.ExportId=e.ExportId
  WHERE c.CreadoUtc<DATEADD(DAY,-7,SYSUTCDATETIME());
 DELETE FROM dbo.ExportControl WHERE CreadoUtc<DATEADD(DAY,-7,SYSUTCDATETIME());
 SELECT @id AS ExportId,@corte AS CorteUtc,@n AS FilasEsperadas;
END;
GO
-- Rol del lector del SHIR: ejecutar la exportación y leer solo lo exportado.
IF DATABASE_PRINCIPAL_ID('rol_origen_lector') IS NULL CREATE ROLE rol_origen_lector;
GRANT EXECUTE ON dbo.usp_CrearExportacion TO rol_origen_lector;
GRANT SELECT ON dbo.DeudaExport TO rol_origen_lector;
GO
