import { defineConfig } from "vite";

// O site é servido pelo servidor central em /web/ (src/ipe/web_dist). Sem mapas de fonte no pacote.
export default defineConfig({
  base: "/web/",
  // o vtk.js (por baixo do Cornerstone3D) usa o xmlbuilder2, que estende o EventEmitter do Node
  resolve: { alias: { events: "events/" } },
  build: {
    outDir: "../src/ipe/web_dist",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
    minify: process.env.IPE_SEM_MINIFY ? false : "terser",
    chunkSizeWarningLimit: 8000,
    // 0.100.0: o xmlbuilder2 (CommonJS, com dependências circulares) às vezes quebrava na carga do pacote minificado
    // ("Object.defineProperty called on non-object") conforme a ordem dos módulos mudava; com strictRequires cada
    // require roda na hora certa, como no Node
    commonjsOptions: { strictRequires: true },
  },
  worker: { format: "es" },
  optimizeDeps: {
    exclude: ["@cornerstonejs/dicom-image-loader"],
    include: ["dicom-parser"],
  },
});
