# Ipê Web — o visualizador do servidor central

Fontes do visualizador no navegador (0.99.91 em diante; plano em `plano-visualizador-web.md`).
O site construído fica em `src/ipe/web_dist/` e vai junto com o Ipê: quem instala não precisa de Node.

Para construir de novo (só quem mexe no site):

```
cd web
npm ci
npm run build        # gera ../src/ipe/web_dist
```

- TypeScript + Vite; Cornerstone3D (MIT) para os quadros, com os codecs em WebAssembly.
- O servidor (Python, `src/ipe/central/server.py` e `web.py`) serve o site em `/web/` e os dados pelo DICOMweb.
- Testes: `tests/test_web_servidor.py` (servidor) e `tests/test_web_e2e.py` (Chromium do Playwright).
