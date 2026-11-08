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
  },
  worker: { format: "es" },
  optimizeDeps: {
    exclude: ["@cornerstonejs/dicom-image-loader"],
    include: ["dicom-parser"],
  },
});
