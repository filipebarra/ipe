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
; 0.99.67: a pasta do programa é perguntada sempre (também numa atualização, já preenchida com a de antes)
DisableDirPage=no
UsePreviousAppDir=yes
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
english.BancoTitulo=Database folder
english.BancoSub=Where the database and the imported studies are kept.
english.BancoTexto=The index (SQLite) and the files copied on import go here; it can be another drive (D:\, an external disk). Uninstalling the program does not delete this folder. If this computer already has a database with studies, keep its folder: to move it later, use Settings ▸ Database ▸ Change the folder of this computer's database, in the program.
english.BancoRotulo=Database folder:
english.ProgFilesAviso=The program installs without administrator rights, so it cannot go into Program Files. Choose a folder of your own (the suggested one, or e.g. D:\Ipe).
english.BancoDentroApp=Choose a database folder outside the program folder (the program folder is replaced on every update).
english.BancoNaoTrocou=The database folder was not changed: the current one (%1) already has studies and the new one is empty. To take the studies to the new folder, open the program and use Settings ▸ Database ▸ Change the folder of this computer's database.
english.VcTitulo=Visual C++ Redistributable
english.VcTexto=This computer does not have the Microsoft Visual C++ Redistributable (x64). Ipê opens without it, but the organ segmentation (TotalSegmentator/PyTorch) needs it.%n%nOpen the Microsoft download page now? (Install it before running the segmentation installer.)
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
brazilianportuguese.BancoTitulo=Pasta do banco de dados
brazilianportuguese.BancoSub=Onde ficam o banco e os exames importados.
brazilianportuguese.BancoTexto=Aqui vão o índice (SQLite) e os arquivos copiados na importação; pode ser outro disco (D:\, um HD externo). Desinstalar o programa não apaga esta pasta. Se este computador já tem um banco com exames, mantenha a pasta dele: para mudar depois, use no programa Configurações ▸ Banco de dados ▸ Mudar a pasta do banco deste computador.
brazilianportuguese.BancoRotulo=Pasta do banco:
brazilianportuguese.ProgFilesAviso=O programa instala sem administrador e por isso não pode ir para Arquivos de Programas. Escolha uma pasta sua (a sugerida, ou por exemplo D:\Ipe).
brazilianportuguese.BancoDentroApp=Escolha a pasta do banco fora da pasta do programa (a pasta do programa é trocada a cada atualização).
brazilianportuguese.BancoNaoTrocou=A pasta do banco não foi trocada: a de agora (%1) já tem exames e a nova está vazia. Para levar os exames para a pasta nova, abra o programa e use Configurações ▸ Banco de dados ▸ Mudar a pasta do banco deste computador.
brazilianportuguese.VcTitulo=Visual C++ Redistributable
brazilianportuguese.VcTexto=Este computador não tem o Microsoft Visual C++ Redistributable (x64). O Ipê abre sem ele, mas a segmentação de órgãos (TotalSegmentator/PyTorch) precisa dele.%n%nAbrir agora o download da Microsoft? (Instale antes de rodar o instalador da segmentação.)
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
spanish.BancoTitulo=Carpeta de la base de datos
spanish.BancoSub=Dónde se guardan la base y los estudios importados.
spanish.BancoTexto=Aquí van el índice (SQLite) y los archivos copiados al importar; puede ser otro disco (D:\, un disco externo). Desinstalar el programa no borra esta carpeta. Si este equipo ya tiene una base con estudios, mantenga su carpeta: para cambiarla después, use en el programa Configuración ▸ Base de datos ▸ Cambiar la carpeta de la base de este equipo.
spanish.BancoRotulo=Carpeta de la base:
spanish.ProgFilesAviso=El programa se instala sin administrador y por eso no puede ir a Archivos de programa. Elija una carpeta suya (la sugerida o, por ejemplo, D:\Ipe).
spanish.BancoDentroApp=Elija la carpeta de la base fuera de la carpeta del programa (la carpeta del programa se reemplaza en cada actualización).
spanish.BancoNaoTrocou=La carpeta de la base no se cambió: la actual (%1) ya tiene estudios y la nueva está vacía. Para llevar los estudios a la carpeta nueva, abra el programa y use Configuración ▸ Base de datos ▸ Cambiar la carpeta de la base de este equipo.
spanish.VcTitulo=Visual C++ Redistributable
spanish.VcTexto=Este equipo no tiene el Microsoft Visual C++ Redistributable (x64). Ipê abre sin él, pero la segmentación de órganos (TotalSegmentator/PyTorch) lo necesita.%n%n¿Abrir ahora la descarga de Microsoft? (Instálelo antes de ejecutar el instalador de la segmentación.)

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
; 0.99.70: numa atualização silenciosa (pelo GitHub ou pelo servidor central) a página não aparece e nada disto roda:
; o modo de uso e o idioma ficam como estavam (antes, voltavam para "só eu" e para o inglês).
Filename: "{app}\{#Cli}"; Parameters: "set-mode single"; Flags: runhidden waituntilterminated; Check: EhUmUsuarioSo
Filename: "{app}\{#Cli}"; Parameters: "set-mode multi"; Flags: runhidden waituntilterminated; Check: NaoEhUmUsuarioSo
; O idioma do programa: o mesmo escolhido na primeira tela do instalador (só na primeira instalação).
Filename: "{app}\{#Cli}"; Parameters: "set-language en"; Flags: runhidden waituntilterminated; Languages: english; Check: NaoEhAtualizacao
Filename: "{app}\{#Cli}"; Parameters: "set-language pt-BR"; Flags: runhidden waituntilterminated; Languages: brazilianportuguese; Check: NaoEhAtualizacao
Filename: "{app}\{#Cli}"; Parameters: "set-language es"; Flags: runhidden waituntilterminated; Languages: spanish; Check: NaoEhAtualizacao
; Registra o link ipe:// para este usuário (HKCU, sem administrador).
Filename: "{app}\{#Cli}"; Parameters: "register-url"; Flags: runhidden waituntilterminated; Tasks: urlscheme
Filename: "{app}\{#Exe}"; Description: "{cm:AbrirAgora}"; Flags: nowait postinstall skipifsilent
; 0.99.70: a atualização pedida pelo programa (/REABRIR=1) abre a versão nova no fim
Filename: "{app}\{#Exe}"; Flags: nowait; Check: Reabrir

[UninstallRun]
Filename: "{app}\{#Cli}"; Parameters: "unregister-url"; Flags: runhidden; RunOnceId: "tiraurl"

; NÃO apagamos banco, exames nem configurações na desinstalação (nem a pasta do banco escolhida na instalação): eles ficam na pasta de
; dados do usuário e são dele. Quem quiser apagar faz pela tela de locais do programa.

[Code]
// Na instalação: a pasta do banco (0.99.67) e se este computador é seu ou de mais gente.
var PaginaQuemUsa: TInputOptionWizardPage;
var PaginaBanco: TInputDirWizardPage;
// 0.99.70: lido ANTES de instalar (depois, a chave do desinstalador já existe também na primeira instalação)
var JaInstalado: Boolean;

function InitializeSetup(): Boolean;
begin
  JaInstalado := RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7B3A9C2E-5D41-4C8A-9E17-DC0F2A6B8E41}_is1');
  Result := True;
end;

// A pasta de agora: o programa grava em HKCU\Software\Ipe (DataDir) ao abrir; sem isso, a padrão.
function PastaDoBanco(): String;
begin
  if not RegQueryStringValue(HKCU, 'Software\Ipe', 'DataDir', Result) or (Result = '') then
    Result := ExpandConstant('{localappdata}\DicomViewer');
end;

function ComecaCom(const Texto, Inicio: String): Boolean;
begin
  Result := (Length(Inicio) > 0) and (Pos(Lowercase(AddBackslash(Inicio)), Lowercase(AddBackslash(Texto))) = 1);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if ComecaCom(WizardDirValue, ExpandConstant('{commonpf64}')) or ComecaCom(WizardDirValue, ExpandConstant('{commonpf32}')) then
    begin
      MsgBox(CustomMessage('ProgFilesAviso'), mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = PaginaBanco.ID then
  begin
    if ComecaCom(PaginaBanco.Values[0], WizardDirValue) then
    begin
      MsgBox(CustomMessage('BancoDentroApp'), mbError, MB_OK);
      Result := False;
    end;
  end;
end;

// 0.99.72: o PyTorch da segmentação precisa do Visual C++ 2015-2022 x64 (o Ipê em si, não)
const URL_VCREDIST = 'https://aka.ms/vs/17/release/vc_redist.x64.exe';

function TemVisualCpp(): Boolean;
var V: Cardinal;
begin
  Result := (RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', V) and (V = 1))
    or (FileExists(ExpandConstant('{sys}\vcruntime140_1.dll')) and FileExists(ExpandConstant('{sys}\msvcp140.dll')));
end;

procedure AvisarVisualCpp();
var Rc: Integer;
begin
  if WizardSilent() or TemVisualCpp() then
    exit;
  if MsgBox(CustomMessage('VcTexto'), mbConfirmation, MB_YESNO) = IDYES then
    ShellExec('open', URL_VCREDIST, '', '', SW_SHOWNORMAL, ewNoWait, Rc);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Pasta: String; Rc: Integer;
begin
  if CurStep <> ssPostInstall then
    exit;
  AvisarVisualCpp();
  Pasta := PaginaBanco.Values[0];
  if Pasta = '' then
    exit;
  // "D:\" terminaria em \" e o Windows leria a aspa como parte do texto
  if Copy(Pasta, Length(Pasta), 1) = '\' then
    Pasta := Pasta + '.';
  // 3 = o banco de agora já tem exames e a pasta nova está vazia: não troca (mover é pelo programa)
  if Exec(ExpandConstant('{app}\{#Cli}'), 'set-data-dir "' + Pasta + '"', '', SW_HIDE, ewWaitUntilTerminated, Rc)
     and (Rc = 3) and not WizardSilent() then
    MsgBox(FmtMessage(CustomMessage('BancoNaoTrocou'), [PastaDoBanco()]), mbInformation, MB_OK);
end;

procedure InitializeWizard();
begin
  PaginaBanco := CreateInputDirPage(wpSelectDir, CustomMessage('BancoTitulo'), CustomMessage('BancoSub'),
    CustomMessage('BancoTexto'), False, 'DicomViewer');
  PaginaBanco.Add(CustomMessage('BancoRotulo'));
  PaginaBanco.Values[0] := PastaDoBanco();
  PaginaQuemUsa := CreateInputOptionPage(
    wpSelectTasks, CustomMessage('QuemTitulo'), CustomMessage('QuemSub'), CustomMessage('QuemTexto'),
    True, False);
  PaginaQuemUsa.Add(CustomMessage('QuemSo'));
  PaginaQuemUsa.Add(CustomMessage('QuemVarios'));
  PaginaQuemUsa.SelectedValueIndex := 0;
end;

// Já havia o Ipê instalado para este usuário (a chave do desinstalador existe)?
function EhAtualizacao(): Boolean;
begin
  Result := JaInstalado;
end;

function NaoEhAtualizacao(): Boolean;
begin
  Result := not EhAtualizacao();
end;

// a pergunta "quem usa" só vale quando foi vista: numa atualização silenciosa, o modo fica como estava
function PerguntaQuemUsaValeu(): Boolean;
begin
  Result := not (WizardSilent() and EhAtualizacao());
end;

function EhUmUsuarioSo(): Boolean;
begin
  Result := PerguntaQuemUsaValeu() and (PaginaQuemUsa.SelectedValueIndex = 0);
end;

function NaoEhUmUsuarioSo(): Boolean;
begin
  Result := PerguntaQuemUsaValeu() and (PaginaQuemUsa.SelectedValueIndex = 1);
end;

function Reabrir(): Boolean;
begin
  Result := ExpandConstant('{param:REABRIR|0}') = '1';
end;
