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
; 0.99.33: a primeira tela pergunta o idioma, com o inglês marcado (não segue o idioma do Windows).
; O idioma escolhido vale para o instalador e para o programa (set-language, no [Run]).
ShowLanguageDialog=yes
LanguageDetectionMethod=none

[Languages]
; o primeiro é o padrão
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.TarefaAtalho=Create a desktop shortcut
english.GrupoAtalhos=Shortcuts:
english.TarefaUrl=Open ipe:// links (and the old dicomviewer:// ones) with this program
english.GrupoIntegracao=Integration:
english.AbrirAgora=Open {#Nome} now
english.QuemTitulo=Who will use {#Nome}
english.QuemSub=This decides whether the program asks for a login when it opens.
english.QuemTexto=This is not final: user accounts are still in the program, under User ▸ Users, and once a user account exists the login is asked for.
english.QuemSo=Only I use this computer — open without asking for a login and password
english.QuemVarios=More than one person uses it — ask for a login, starting with the administrator account
brazilianportuguese.TarefaAtalho=Criar atalho na área de trabalho
brazilianportuguese.GrupoAtalhos=Atalhos:
brazilianportuguese.TarefaUrl=Abrir links ipe:// (e os antigos dicomviewer://) com este programa
brazilianportuguese.GrupoIntegracao=Integração:
brazilianportuguese.AbrirAgora=Abrir o {#Nome} agora
brazilianportuguese.QuemTitulo=Quem vai usar o {#Nome}
brazilianportuguese.QuemSub=Isso decide se o programa pede login ao abrir.
brazilianportuguese.QuemTexto=A escolha não é definitiva: o cadastro de usuários continua no programa, em Usuário ▸ Usuários, e a partir do momento em que existir um usuário cadastrado o login passa a ser pedido.
brazilianportuguese.QuemSo=Só eu uso este computador — abrir sem pedir login e senha
brazilianportuguese.QuemVarios=Mais de uma pessoa usa — pedir login, começando pelo cadastro do administrador
spanish.TarefaAtalho=Crear un acceso directo en el escritorio
spanish.GrupoAtalhos=Accesos directos:
spanish.TarefaUrl=Abrir los enlaces ipe:// (y los antiguos dicomviewer://) con este programa
spanish.GrupoIntegracao=Integración:
spanish.AbrirAgora=Abrir {#Nome} ahora
spanish.QuemTitulo=Quién va a usar {#Nome}
spanish.QuemSub=Esto decide si el programa pide inicio de sesión al abrir.
spanish.QuemTexto=La elección no es definitiva: el registro de usuarios sigue en el programa, en Usuario ▸ Usuarios, y desde el momento en que exista un usuario registrado se pide el inicio de sesión.
spanish.QuemSo=Solo yo uso este equipo — abrir sin pedir usuario y contraseña
spanish.QuemVarios=Lo usa más de una persona — pedir inicio de sesión, empezando por el registro del administrador

[Tasks]
Name: "desktopicon"; Description: "{cm:TarefaAtalho}"; GroupDescription: "{cm:GrupoAtalhos}"
Name: "urlscheme"; Description: "{cm:TarefaUrl}"; GroupDescription: "{cm:GrupoIntegracao}"

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
; O idioma do programa: o mesmo escolhido na primeira tela do instalador.
Filename: "{app}\{#Cli}"; Parameters: "set-language en"; Flags: runhidden waituntilterminated; Languages: english
Filename: "{app}\{#Cli}"; Parameters: "set-language pt-BR"; Flags: runhidden waituntilterminated; Languages: brazilianportuguese
Filename: "{app}\{#Cli}"; Parameters: "set-language es"; Flags: runhidden waituntilterminated; Languages: spanish
; Registra o link ipe:// para este usuário (HKCU, sem administrador).
Filename: "{app}\{#Cli}"; Parameters: "register-url"; Flags: runhidden waituntilterminated; Tasks: urlscheme
Filename: "{app}\{#Exe}"; Description: "{cm:AbrirAgora}"; Flags: nowait postinstall skipifsilent

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
    wpSelectTasks, CustomMessage('QuemTitulo'), CustomMessage('QuemSub'), CustomMessage('QuemTexto'),
    True, False);
  PaginaQuemUsa.Add(CustomMessage('QuemSo'));
  PaginaQuemUsa.Add(CustomMessage('QuemVarios'));
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
