-- Hub de Deuda — esquema base (Anexo A de la guía, completado)
-- Ejecutar en una base vacía (HubDeuda en Azure SQL o HubDeuda_* local).
-- Las tablas guardan versiones históricas; los punteros vigentes solo se
-- cambian mediante los procedimientos de 003_procedimientos.sql.

CREATE TABLE dbo.Area (
 AreaId tinyint PRIMARY KEY CHECK (AreaId BETWEEN 1 AND 10),
 Nombre nvarchar(80) NOT NULL,
 TipoPermitido varchar(12) NOT NULL
   CHECK (TipoPermitido IN ('PAGO','CARGO','DESCUENTO','OBSERVACION')),
 LoteVigente uniqueidentifier NULL
);
INSERT dbo.Area (AreaId,Nombre,TipoPermitido) VALUES
(1,N'Tesorería','PAGO'),
(2,N'Ejecutoría Coactiva','CARGO'),
(3,N'Asesoría Legal','OBSERVACION'),
(4,N'Fiscalización','OBSERVACION'),
(5,N'Atención al Ciudadano','OBSERVACION'),
(6,N'Recaudación','OBSERVACION'),
(7,N'Administración Tributaria','DESCUENTO'),
(8,N'Contabilidad','OBSERVACION'),
(9,N'Tránsito','OBSERVACION'),
(10,N'Archivo Central','OBSERVACION');

-- Archivo autorizado por área (espejo controlado de la lista ConfigAreas de
-- SharePoint). La Function rechaza manifiestos cuyo sourceFileId no coincida.
CREATE TABLE dbo.AreaFuente (
 AreaId tinyint PRIMARY KEY REFERENCES dbo.Area(AreaId),
 ArchivoId nvarchar(200) NOT NULL,
 RutaArchivo nvarchar(400) NOT NULL,
 Activa bit NOT NULL DEFAULT 1,
 ResponsableUPN nvarchar(200) NULL,
 DestinoAvisos nvarchar(200) NULL,
 VersionContrato varchar(10) NOT NULL DEFAULT '1'
);

CREATE TABLE dbo.BaseCarga (
 CargaId uniqueidentifier PRIMARY KEY,
 CorteUtc datetime2 NOT NULL,
 Estado varchar(20) NOT NULL
   CHECK (Estado IN ('RECIBIDA','ACEPTADA','FALLIDA')),
 FilasEsperadas int NOT NULL,
 CreadaUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 PublicadaUtc datetime2 NULL,
 Motivo nvarchar(500) NULL
);
CREATE TABLE dbo.BaseFila (
 CargaId uniqueidentifier NOT NULL
   REFERENCES dbo.BaseCarga(CargaId),
 PapeletaId varchar(30) NOT NULL,
 TipoDoc varchar(3) NOT NULL CHECK (TipoDoc IN ('DNI','RUC')),
 Documento varchar(11) NOT NULL,
 Placa varchar(10) NULL,
 ImporteOriginal decimal(18,2) NOT NULL
   CHECK (ImporteOriginal >= 0),
 Activa bit NOT NULL,
 PRIMARY KEY (CargaId,PapeletaId)
);
CREATE INDEX IX_BaseFila_Documento ON dbo.BaseFila(CargaId,Documento);
CREATE INDEX IX_BaseFila_Placa ON dbo.BaseFila(CargaId,Placa);
CREATE TABLE dbo.BaseActual (
 Id tinyint PRIMARY KEY CHECK (Id=1),
 CargaId uniqueidentifier NULL
   REFERENCES dbo.BaseCarga(CargaId)
);
INSERT dbo.BaseActual VALUES (1,NULL);
GO

CREATE TABLE dbo.Lote (
 LoteId uniqueidentifier PRIMARY KEY,
 AreaId tinyint NOT NULL REFERENCES dbo.Area(AreaId),
 ArchivoId nvarchar(200) NOT NULL,
 VersionFuente nvarchar(120) NOT NULL,
 ModificadoUtc datetime2 NOT NULL,
 Reglas varchar(10) NOT NULL,
 Sha256 char(64) NOT NULL,
 RawPath nvarchar(1000) NOT NULL,
 Estado varchar(20) NOT NULL CHECK (Estado IN ('RECIBIDO','VALIDADO',
   'ACEPTADO','RECHAZADO','SIN_CAMBIOS','OBSOLETO','CONFLICTO')),
 FilasLeidas int NOT NULL,
 FlowRunId nvarchar(200) NULL,
 SolicitadoPor nvarchar(200) NULL,
 CreadoUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 PublicadoUtc datetime2 NULL
);
ALTER TABLE dbo.Area ADD CONSTRAINT FK_Area_Lote
 FOREIGN KEY (LoteVigente) REFERENCES dbo.Lote(LoteId);
CREATE TABLE dbo.Movimiento (
 LoteId uniqueidentifier NOT NULL REFERENCES dbo.Lote(LoteId),
 MovimientoId varchar(50) NOT NULL,
 PapeletaId varchar(30) NOT NULL,
 Tipo varchar(12) NOT NULL CHECK
  (Tipo IN ('PAGO','CARGO','DESCUENTO','OBSERVACION')),
 Monto decimal(18,2) NOT NULL,
 FechaEvento date NOT NULL,
 Estado varchar(8) NOT NULL
  CHECK (Estado IN ('ACTIVO','ANULADO')),
 Referencia nvarchar(100) NOT NULL,
 Detalle nvarchar(250) NULL,
 FilaExcel int NOT NULL,
 PRIMARY KEY (LoteId,MovimientoId),
 CHECK ((Tipo='OBSERVACION' AND Monto=0) OR
        (Tipo<>'OBSERVACION' AND Monto>0))
);
CREATE TABLE dbo.Observacion (
 ObservacionId bigint IDENTITY PRIMARY KEY,
 LoteId uniqueidentifier NOT NULL REFERENCES dbo.Lote(LoteId),
 FilaExcel int NULL,
 Campo nvarchar(50) NOT NULL,
 Codigo varchar(40) NOT NULL,
 Mensaje nvarchar(500) NOT NULL,
 -- Lote aceptado posterior que subsana el error (11.9: corregido ≠ oculto)
 SubsanadaPor uniqueidentifier NULL REFERENCES dbo.Lote(LoteId)
);
CREATE INDEX IX_Mov_Papeleta ON dbo.Movimiento(PapeletaId);
CREATE INDEX IX_Lote_Area ON dbo.Lote(AreaId,ModificadoUtc);
CREATE INDEX IX_Obs_Lote ON dbo.Observacion(LoteId);
GO

-- Cola de avisos (12.1). Clave única evita avisos duplicados por lote.
CREATE TABLE dbo.Notificacion (
 NotificacionId bigint IDENTITY PRIMARY KEY,
 LoteId uniqueidentifier NOT NULL REFERENCES dbo.Lote(LoteId),
 TipoAviso varchar(20) NOT NULL,
 Estado varchar(12) NOT NULL DEFAULT 'PENDIENTE'
   CHECK (Estado IN ('PENDIENTE','ENVIADO','EN_REVISION')),
 Intentos int NOT NULL DEFAULT 0,
 MensajeId nvarchar(200) NULL,
 CreadaUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
 EnviadaUtc datetime2 NULL,
 CONSTRAINT UQ_Notificacion UNIQUE (LoteId,TipoAviso)
);

-- Control operativo de manifiestos (10: intentos, último error y próximo
-- reintento). Un fallo técnico no es terminal; un resultado de negocio sí.
CREATE TABLE dbo.ProcesoManifiesto (
 Manifiesto nvarchar(300) PRIMARY KEY,
 LoteId uniqueidentifier NULL,
 Intentos int NOT NULL DEFAULT 0,
 UltimoError nvarchar(1000) NULL,
 ProximoIntentoUtc datetime2 NULL,
 Terminal bit NOT NULL DEFAULT 0,
 ActualizadoUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
