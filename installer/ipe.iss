; Instalador do Ipê — Inno Setup 6
;
; Instala NO PERFIL DO USUÁRIO: nada de administrador, nada em Arquivos de Programas.
; É a mesma regra do programa, que nunca roda elevado.
;
; Até a 0.99.10 o programa se chamava DicomViewer. O AppId é o mesmo: o instalador novo atualiza o
; antigo no lugar (mesma pasta, mesmos dados) e tira os atalhos e executáveis com o nome velho.
;
; Compilar:  iscc installer\ipe.iss  (ou pelo build_windows.bat, que faz tudo)

#define Nome "Ipê"
; sem acento: pasta, executáveis e arquivo do instalador
#define Arq "Ipe"
#define Exe "Ipe.exe"
#define Cli "ipe-cli.exe"
#ifndef Versao
  #define Versao "0.0.0"
#endif

[Setup]
AppId={{7B3A9C2E-5D41-4C8A-9E17-DC0F2A6B8E41}
AppName={#Nome}
AppVersion={#Versao}
AppVerName={#Nome} {#Versao}
AppPublisher=Filipe Ramos Barra
DefaultDirName={localappdata}\Programs\{#Arq}
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename={#Arq}-{#Versao}-instalador
SetupIconFile=ipe.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nome} {#Versao}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
LicenseFile=
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"
Name: "urlscheme"; Description: "Abrir links ipe:// (e os antigos dicomviewer://) com este programa"; GroupDescription: "Integração:"

[Files]
; A pasta inteira que o PyInstaller gerou.
Source: "..\dist\{#Arq}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; o que sobrou do nome antigo (DicomViewer), numa atualização
Type: files; Name: "{app}\DicomViewer.exe"
Type: files; Name: "{app}\dicomviewer-cli.exe"
Type: filesandordirs; Name: "{app}\_internal\dicomviewer"
Type: files; Name: "{autoprograms}\DicomViewer.lnk"
Type: files; Name: "{autodesktop}\DicomViewer.lnk"

[Icons]
Name: "{autoprograms}\{#Nome}"; Filename: "{app}\{#Exe}"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\{#Exe}"; Tasks: desktopicon

[Run]
; Quem usa este computador. "single" abre sem pedir login; o cadastro de usuários continua lá,
; e no dia em que existir um usuário cadastrado o login volta a ser pedido.
Filename: "{app}\{#Cli}"; Parameters: "set-mode single"; Flags: runhidden waituntilterminated; Check: EhUmUsuarioSo
Filename: "{app}\{#Cli}"; Parameters: "set-mode multi"; Flags: runhidden waituntilterminated; Check: NaoEhUmUsuarioSo
; Registra o link ipe:// para este usuário (HKCU, sem administrador).
Filename: "{app}\{#Cli}"; Parameters: "register-url"; Flags: runhidden waituntilterminated; Tasks: urlscheme
Filename: "{app}\{#Exe}"; Description: "Abrir o {#Nome} agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#Cli}"; Parameters: "unregister-url"; Flags: runhidden; RunOnceId: "tiraurl"

; NÃO apagamos banco, exames nem configurações na desinstalação: eles ficam na pasta de
; dados do usuário e são dele. Quem quiser apagar faz pela tela de locais do programa.

[Code]
// Uma pergunta só, na instalação: este computador é seu ou de mais gente?
var PaginaQuemUsa: TInputOptionWizardPage;

procedure InitializeWizard();
begin
  PaginaQuemUsa := CreateInputOptionPage(
    wpSelectTasks,
    'Quem vai usar o {#Nome}',
    'Isso decide se o programa pede login ao abrir.',
    'A escolha não é definitiva: o cadastro de usuários continua no programa, em Usuário ▸ Usuários, ' +
    'e a partir do momento em que existir um usuário cadastrado o login passa a ser pedido.',
    True, False);
  PaginaQuemUsa.Add('Só eu uso este computador — abrir sem pedir login e senha');
  PaginaQuemUsa.Add('Mais de uma pessoa usa — pedir login, começando pelo cadastro do administrador');
  PaginaQuemUsa.SelectedValueIndex := 0;
end;

function EhUmUsuarioSo(): Boolean;
begin
  Result := PaginaQuemUsa.SelectedValueIndex = 0;
end;

function NaoEhUmUsuarioSo(): Boolean;
begin
  Result := not EhUmUsuarioSo();
end;
