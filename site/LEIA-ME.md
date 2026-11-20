# Site do Ipê

Publicado pelo GitHub Pages em <https://filipebarra.github.io/ipe/> (inglês), `/pt/` e `/es/`.

- **Textos:** `conteudo.py` — cada texto é `T(en, pt, es)`. O site é organizado por **tarefa do dia**
  (`TAREFAS`): cada tarefa tem um clipe principal, clipes extras, passos e "o que mais tem aqui".
- **Gerar:** `python site/gerar.py` (só a biblioteca padrão) → `_site/`. O workflow `.github/workflows/site.yml`
  faz isso e publica a cada mudança em `site/` na `main`.
- **Clipes** (curtos, sem som, em laço): `media/clipes/<en|pt|es>/<nome>.mp4` e o pôster `<nome>.jpg`, gravados do
  próprio Ipê com exames de exemplo **anonimizados** (EXEMPLO^…). Falta o de um idioma? O site usa o inglês.
- **Tutoriais** (longos, com legenda): `media/tutoriais/<id>-<lingua>.mp4` e `.jpg`, listados em `TUTORIAIS`.
  Publicou no YouTube? Ponha o código do vídeo em `"youtube": {"pt": "…", "en": "…"}` e o site passa a mostrar o
  YouTube (sem cookies, `youtube-nocookie.com`), com o link "Ver no YouTube".
- **Nunca** pôr no site imagem ou vídeo com dado de paciente real.

Primeira vez: no GitHub, **Settings ▸ Pages ▸ Build and deployment ▸ Source: GitHub Actions**.
