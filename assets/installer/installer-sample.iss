; ArcIA — Enterprise Agentic AI Platform
; Inno Setup Demonstration Script

#define MyAppName "ArcIA Enterprise Platform"
#define MyAppVersion "0.4.0"
#define MyAppPublisher "ArcIA Platform"
#define MyAppURL "https://assistant.example.org"

[Setup]
AppId={{8A9E4F20-6C5B-4B9E-9F1A-2D3C4E5F6A7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\ArcIA
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=ArcIA-Setup-{#MyAppVersion}
SetupIconFile=assets\installer\app.ico
WizardImageFile=assets\installer\wizard-side.bmp
WizardSmallImageFile=assets\installer\wizard-header.bmp
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "assets\branding\*"; DestDir: "{app}\assets\branding"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\installer\app.ico"; DestDir: "{app}\assets\installer"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}"; IconFilename: "{app}\assets\installer\app.ico"
