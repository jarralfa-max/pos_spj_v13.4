; SPJ ERP/POS — Inno Setup 6 script.
;
; Built by scripts/release/build_windows_release.py, which passes:
;   /DAppVersion=13.5.0            semantic version (app_version.VERSION)
;   /DFileVersion=13.5.0.0         4-part numeric version
;   /DSourceDir=...\dist\SPJ       PyInstaller one-folder output
;   /DUpdaterExe=...\spj_updater.exe
;   /DBuildDir=...                 version_info, icon, build_info
;   /DOutputDir=...                where SPJ-Setup-<ver>-x64.exe is written
;   /DFeedUrl=https://.../{channel}/manifest.json   (may be empty)
;   /DAllowedHosts=host1,host2                     (may be empty)
;   /DDefaultChannel=stable
;   /DSIGN                         only when a code-signing certificate exists
;
; Silent-install parameters understood by this script (besides Inno's own
; /SILENT /VERYSILENT /DIR= /TYPE= /COMPONENTS= /TASKS= /LOG=):
;   /DATASCOPE=machine|user   /CHANNEL=stable|pilot   /LEGACYDB=<path>
;   /SPJUPDATER=1  (set by the external updater: no launch at the end)
;
; Data is NEVER removed by uninstall, repair or upgrade: the database,
; backups, logs, images, secrets fallback and WhatsApp conversations live in
; the data folder (ProgramData or LocalAppData), not in {app}.

#ifndef AppVersion
  #error "AppVersion no definido: use scripts/release/build_windows_release.py"
#endif
#ifndef DefaultChannel
  #define DefaultChannel "stable"
#endif
#ifndef FeedUrl
  #define FeedUrl ""
#endif
#ifndef AllowedHosts
  #define AllowedHosts ""
#endif
#ifndef BuildDir
  #define BuildDir "."
#endif

#define AppName "SPJ ERP POS"
#define Publisher "SPJ"
#define Arch "x64"
#define InstallerCacheDir "{commonappdata}\SPJ\Installers\SPJ ERP POS"
#define InstallerName "SPJ-Setup-" + AppVersion + "-" + Arch + ".exe"

[Setup]
; NEVER change AppId: it is how Windows and Inno recognise an existing
; installation to upgrade/repair it instead of installing a second copy.
AppId={{283B150A-0E75-4CD2-97F6-B425F58BF260}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
VersionInfoVersion={#FileVersion}
VersionInfoProductVersion={#FileVersion}
VersionInfoProductTextVersion={#AppVersion}
DefaultDirName={autopf}\SPJ\{#AppName}
DefaultGroupName=SPJ
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousSetupType=yes
UsePreviousComponents=yes
UsePreviousTasks=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
OutputDir={#OutputDir}
OutputBaseFilename=SPJ-Setup-{#AppVersion}-{#Arch}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SPJ.exe
UninstallDisplayName={#AppName}
#if FileExists(BuildDir + "\spj.ico")
SetupIconFile={#BuildDir}\spj.ico
#endif
#ifdef SIGN
SignTool=spjsign
SignedUninstaller=yes
#endif

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Types]
Name: "pos_essential"; Description: "POS esencial (venta, caja, catálogo, inventario, clientes, fidelidad)"
Name: "erp_full"; Description: "ERP completo (todos los módulos)"
Name: "custom"; Description: "Personalizado"; Flags: iscustom

[Components]
Name: "nucleo"; Description: "Núcleo: punto de venta, caja, productos, inventario, precios, clientes y configuración"; Types: pos_essential erp_full custom; Flags: fixed
Name: "modulos"; Description: "Módulos"; Types: pos_essential erp_full
Name: "modulos\fidelidad"; Description: "Fidelidad y tarjetas"; Types: pos_essential erp_full
Name: "modulos\orders_delivery"; Description: "Pedidos y entregas"; Types: erp_full
Name: "modulos\purchasing"; Description: "Compras y proveedores"; Types: erp_full
Name: "modulos\transfers"; Description: "Transferencias"; Types: erp_full
Name: "modulos\losses"; Description: "Mermas"; Types: erp_full
Name: "modulos\meat_processing"; Description: "Procesamiento cárnico"; Types: erp_full
Name: "modulos\finance"; Description: "Finanzas y contabilidad"; Types: erp_full
Name: "modulos\hr"; Description: "Recursos humanos y nómina (incluye Finanzas)"; Types: erp_full
Name: "modulos\business_intelligence"; Description: "Inteligencia de negocio"; Types: erp_full
Name: "modulos\assets"; Description: "Activos (incluye Finanzas)"; Types: erp_full
Name: "whatsapp_local"; Description: "Servicio WhatsApp local (opcional; en producción se recomienda el servicio remoto)"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Dirs]
; Machine scope: every Windows user of the station must be able to write the data.
Name: "{commonappdata}\SPJ\{#AppName}"; Permissions: users-modify; Check: IsMachineScope; Flags: uninsneveruninstall
; Rollback installers: written only by this (elevated) installer.
Name: "{#InstallerCacheDir}"; Flags: uninsneveruninstall

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#UpdaterExe}"; DestDir: "{app}"; Flags: ignoreversion
; The installer keeps a copy of itself so the updater can roll back to this
; exact version later (installers.json records its SHA-256).
Source: "{srcexe}"; DestDir: "{#InstallerCacheDir}"; DestName: "{#InstallerName}"; Flags: external ignoreversion uninsneveruninstall

[Icons]
Name: "{autoprograms}\SPJ\{#AppName}"; Filename: "{app}\SPJ.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\SPJ\Reparar {#AppName}"; Filename: "{#InstallerCacheDir}\{#InstallerName}"; Comment: "Vuelve a instalar esta versión sin tocar los datos"
Name: "{autoprograms}\SPJ\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SPJ.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\spj_whatsapp.exe"; Parameters: "--startup auto install"; Flags: runhidden waituntilterminated; Components: whatsapp_local; Check: IsMachineScope; StatusMsg: "Registrando el servicio WhatsApp local…"
Filename: "{app}\spj_whatsapp.exe"; Parameters: "start"; Flags: runhidden waituntilterminated; Components: whatsapp_local; Check: IsMachineScope
Filename: "{app}\SPJ.exe"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent; Check: not IsUpdaterRun

[UninstallRun]
Filename: "{app}\spj_whatsapp.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopWhatsApp"
Filename: "{app}\spj_whatsapp.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveWhatsApp"

[UninstallDelete]
Type: files; Name: "{app}\install_config.json"

[Code]
var
  ScopePage: TInputOptionWizardPage;
  LegacyPage: TInputFileWizardPage;

function ParamOr(const Name, Default: String): String;
begin
  Result := ExpandConstant('{param:' + Name + '|' + Default + '}');
end;

function IsUpdaterRun: Boolean;
begin
  Result := ParamOr('SPJUPDATER', '0') = '1';
end;

function PreviousDataScope: String;
var
  Value: String;
begin
  Result := '';
  if RegQueryStringValue(HKLM, 'Software\SPJ\SPJ ERP POS', 'DataScope', Value) then
    Result := Value;
end;

function IsMachineScope: Boolean;
begin
  if WizardSilent then
    Result := LowerCase(ParamOr('DATASCOPE', PreviousDataScope)) <> 'user'
  else
    Result := ScopePage.SelectedValueIndex = 0;
end;

procedure InitializeWizard;
var
  Previous: String;
begin
  ScopePage := CreateInputOptionPage(wpSelectDir,
    'Ubicación de los datos', '¿Quién usará SPJ en este equipo?',
    'La base de datos, respaldos, imágenes y registros se guardan fuera de la carpeta del programa ' +
    'y NUNCA se borran al actualizar, reparar o desinstalar.',
    True, False);
  ScopePage.Add('Todos los usuarios de Windows de este equipo (recomendado para cajas)  —  C:\ProgramData\SPJ');
  ScopePage.Add('Sólo mi usuario de Windows  —  %LOCALAPPDATA%\SPJ');
  Previous := LowerCase(ParamOr('DATASCOPE', PreviousDataScope));
  if Previous = 'user' then
    ScopePage.SelectedValueIndex := 1
  else
    ScopePage.SelectedValueIndex := 0;

  LegacyPage := CreateInputFilePage(ScopePage.ID,
    'Base de datos anterior (opcional)', '¿Este equipo ya usaba SPJ desde una carpeta?',
    'Si SPJ se ejecutaba desde una carpeta de código (por ejemplo ...\pos_spj_v13.4\data\' +
    'spj_pos_database.db), indíquela: al primer arranque se traslada UNA vez, con respaldo ' +
    'verificado, y el archivo original se conserva renombrado. Déjelo vacío en una instalación nueva.');
  LegacyPage.Add('Archivo spj_pos_database.db anterior:', 'Base SQLite|*.db|Todos|*.*', '.db');
  LegacyPage.Values[0] := ParamOr('LEGACYDB', '');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  { On upgrades the scope and the legacy database were already decided. }
  if (PageID = ScopePage.ID) or (PageID = LegacyPage.ID) then
    Result := PreviousDataScope <> '';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectComponents) and WizardIsComponentSelected('whatsapp_local')
     and not IsMachineScope then
  begin
    MsgBox('El servicio WhatsApp local necesita los datos para todos los usuarios del equipo.',
           mbError, MB_OK);
    Result := False;
  end;
end;

function JsonEscape(const S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

function JsonList(const Csv: String): String;
var
  Rest, Item: String;
  P: Integer;
begin
  Result := '';
  Rest := Csv;
  while Rest <> '' do
  begin
    P := Pos(',', Rest);
    if P = 0 then begin Item := Rest; Rest := ''; end
    else begin Item := Copy(Rest, 1, P - 1); Rest := Copy(Rest, P + 1, Length(Rest)); end;
    Item := Trim(Item);
    if Item <> '' then
    begin
      if Result <> '' then Result := Result + ', ';
      Result := Result + '"' + JsonEscape(Item) + '"';
    end;
  end;
  Result := '[' + Result + ']';
end;

procedure AddIfSelected(var Csv: String; const Name: String);
begin
  if WizardIsComponentSelected('modulos\' + Name) then
  begin
    if Csv <> '' then Csv := Csv + ',';
    Csv := Csv + Name;
  end;
end;

function SelectedCapabilities: String;
begin
  { The runtime closes dependencies (hr/assets -> finance) and always adds the
    core: see backend/domain/software_distribution/install_profile.py. }
  Result := '';
  AddIfSelected(Result, 'fidelidad');
  AddIfSelected(Result, 'orders_delivery');
  AddIfSelected(Result, 'purchasing');
  AddIfSelected(Result, 'transfers');
  AddIfSelected(Result, 'losses');
  AddIfSelected(Result, 'meat_processing');
  AddIfSelected(Result, 'finance');
  AddIfSelected(Result, 'hr');
  AddIfSelected(Result, 'business_intelligence');
  AddIfSelected(Result, 'assets');
end;

function LegacyDatabasePath: String;
begin
  if WizardSilent then
    Result := ParamOr('LEGACYDB', '')
  else
    Result := Trim(LegacyPage.Values[0]);
end;

procedure WriteInstallConfig;
var
  Scope, Channel, Legacy, Json: String;
begin
  if IsMachineScope then Scope := 'machine' else Scope := 'user';
  Channel := LowerCase(ParamOr('CHANNEL', '{#DefaultChannel}'));
  if (Channel <> 'stable') and (Channel <> 'pilot') then Channel := 'stable';
  Legacy := LegacyDatabasePath;
  if Legacy <> '' then Legacy := '"' + JsonEscape(Legacy) + '"';
  Json :=
    '{' + #13#10 +
    '  "format": "spj-install/1",' + #13#10 +
    '  "data_scope": "' + Scope + '",' + #13#10 +
    '  "profile": "' + WizardSetupType(False) + '",' + #13#10 +
    '  "capabilities": ' + JsonList(SelectedCapabilities) + ',' + #13#10 +
    '  "update_channel": "' + Channel + '",' + #13#10 +
    '  "update_feed_url": "' + JsonEscape('{#FeedUrl}') + '",' + #13#10 +
    '  "allowed_update_hosts": ' + JsonList('{#AllowedHosts}') + ',' + #13#10 +
    '  "legacy_database_paths": [' + Legacy + '],' + #13#10 +
    '  "whatsapp_mode": "';
  if WizardIsComponentSelected('whatsapp_local') then
    Json := Json + 'local'
  else
    Json := Json + 'remote';
  Json := Json + '"' + #13#10 + '}' + #13#10;
  if not SaveStringToFile(ExpandConstant('{app}\install_config.json'), Json, False) then
    RaiseException('No se pudo escribir install_config.json');
  RegWriteStringValue(HKLM, 'Software\SPJ\SPJ ERP POS', 'DataScope', Scope);
  RegWriteStringValue(HKLM, 'Software\SPJ\SPJ ERP POS', 'InstalledVersion', '{#AppVersion}');
end;

procedure WriteInstallerIndex;
{ installers.json: name + SHA-256 of each cached installer. Written only by
  this elevated process; the updater refuses any cached file not listed or
  whose hash differs. Keeps this version and the one being replaced. }
var
  Dir, Current, Previous, PreviousName, Json: String;
begin
  Dir := ExpandConstant('{#InstallerCacheDir}');
  Current := '{#InstallerName}';
  Json := '{"installers": [' +
          '{"version": "{#AppVersion}", "file": "' + Current + '", "sha256": "' +
          GetSHA256OfFile(Dir + '\' + Current) + '"}';
  if RegQueryStringValue(HKLM, 'Software\SPJ\SPJ ERP POS', 'PreviousVersion', Previous)
     and (Previous <> '{#AppVersion}') then
  begin
    PreviousName := 'SPJ-Setup-' + Previous + '-{#Arch}.exe';
    if FileExists(Dir + '\' + PreviousName) then
      Json := Json + ', {"version": "' + Previous + '", "file": "' + PreviousName +
              '", "sha256": "' + GetSHA256OfFile(Dir + '\' + PreviousName) + '"}';
  end;
  Json := Json + ']}';
  SaveStringToFile(Dir + '\installers.json', Json, False);
end;

procedure PruneInstallerCache;
var
  FindRec: TFindRec;
  Dir, Keep1, Keep2, Previous: String;
begin
  Dir := ExpandConstant('{#InstallerCacheDir}');
  Keep1 := '{#InstallerName}';
  Keep2 := '';
  if RegQueryStringValue(HKLM, 'Software\SPJ\SPJ ERP POS', 'PreviousVersion', Previous) then
    Keep2 := 'SPJ-Setup-' + Previous + '-{#Arch}.exe';
  if FindFirst(Dir + '\SPJ-Setup-*.exe', FindRec) then
  try
    repeat
      if (CompareText(FindRec.Name, Keep1) <> 0) and (CompareText(FindRec.Name, Keep2) <> 0) then
        DeleteFile(Dir + '\' + FindRec.Name);
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
  Installed: String;
begin
  Result := '';
  { Remember the version being replaced: it becomes the rollback target. }
  if RegQueryStringValue(HKLM, 'Software\SPJ\SPJ ERP POS', 'InstalledVersion', Installed)
     and (Installed <> '{#AppVersion}') then
    RegWriteStringValue(HKLM, 'Software\SPJ\SPJ ERP POS', 'PreviousVersion', Installed);
  { A running local WhatsApp service holds files in {app}: stop it first. }
  if FileExists(ExpandConstant('{app}\spj_whatsapp.exe')) then
    Exec(ExpandConstant('{app}\spj_whatsapp.exe'), 'stop', '', SW_HIDE,
         ewWaitUntilTerminated, Code);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    WriteInstallConfig;
    WriteInstallerIndex;
    PruneInstallerCache;
    if not WizardIsComponentSelected('whatsapp_local') and
       FileExists(ExpandConstant('{app}\spj_whatsapp.exe')) then
      Exec(ExpandConstant('{app}\spj_whatsapp.exe'), 'remove', '', SW_HIDE,
           ewWaitUntilTerminated, Code);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKLM, 'Software\SPJ\SPJ ERP POS', 'InstalledVersion');
    if not UninstallSilent then
      MsgBox('SPJ se desinstaló. Sus datos (base de datos, respaldos, imágenes y registros) se ' +
           'conservaron en la carpeta de datos de SPJ. Bórrelos manualmente sólo si está seguro.',
           mbInformation, MB_OK);
  end;
end;
