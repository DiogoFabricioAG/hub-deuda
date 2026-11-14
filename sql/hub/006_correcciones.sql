-- Registro de correcciones automáticas del saneamiento (versión on-premise):
-- cada valor que el mapeo normaliza queda con su valor original, para poder
-- demostrar qué se limpió y por qué. No altera la decisión del lote.
IF OBJECT_ID('dbo.CorreccionLote') IS NULL
CREATE TABLE dbo.CorreccionLote (
 CorreccionId bigint IDENTITY PRIMARY KEY,
 LoteId uniqueidentifier NOT NULL REFERENCES dbo.Lote(LoteId),
 FilaOriginal int NULL,
 Campo nvarchar(50) NOT NULL,
 ValorOriginal nvarchar(300) NULL,
 ValorCorregido nvarchar(300) NULL,
 Regla varchar(40) NOT NULL,
 CreadoUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_CorreccionLote_Lote')
 CREATE INDEX IX_CorreccionLote_Lote ON dbo.CorreccionLote(LoteId);
GO
GRANT SELECT, INSERT ON dbo.CorreccionLote TO rol_hub_integracion;
GO
