// Site do Ipê: os clipes só carregam e tocam quando aparecem na tela (sem som, em laço); quem prefere menos
// movimento vê o pôster e toca no botão. E uma sugestão discreta de idioma, pela língua do navegador.
(function () {
  "use strict";
  var menosMovimento = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function carregar(v) {
    if (!v.getAttribute("src") && v.dataset.src) { v.src = v.dataset.src; }
  }
  function marcar(v, tocando) {
    var b = v.parentNode.querySelector(".clipe-botao");
    if (!b) return;
    b.classList.toggle("parado", !tocando);
    b.setAttribute("aria-label", tocando ? b.dataset.pausar : b.dataset.tocar);
  }
  function tocar(v) {
    carregar(v);
    var p = v.play();
    if (p && p.catch) p.catch(function () { marcar(v, false); });
    marcar(v, true);
  }
  function pausar(v) { v.pause(); marcar(v, false); }

  var videos = Array.prototype.slice.call(document.querySelectorAll(".clipe video"));
  videos.forEach(function (v) {
    marcar(v, false);
    var b = v.parentNode.querySelector(".clipe-botao");
    if (b) b.addEventListener("click", function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      v.dataset.manual = "1";
      if (v.paused) tocar(v); else pausar(v);
    });
  });
  if ("IntersectionObserver" in window) {
    var obs = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) {
        var v = en.target;
        if (en.isIntersecting) {
          if (!menosMovimento && !v.dataset.manual) tocar(v);
        } else if (!v.paused) { pausar(v); }
      });
    }, { threshold: 0.35 });
    videos.forEach(function (v) { obs.observe(v); });
  }

  // sugestão de idioma (uma vez; a escolha fica neste navegador)
  try {
    var atual = document.body.dataset.lingua;
    var nav = (navigator.language || "en").toLowerCase().slice(0, 2);
    var mapa = window.IPE_LINGUAS || {};
    var visto = localStorage.getItem("ipe-site-lingua");
    if (!visto && nav !== atual && mapa[nav]) {
      var caixa = document.getElementById("sugestao");
      var d = mapa[nav];
      caixa.innerHTML = '<div class="largura"><span lang="' + nav + '">' + d.texto + '</span><a lang="' + nav +
        '" href="' + d.url + '">' + d.ir + '</a><button type="button" aria-label="×">×</button></div>';
      caixa.hidden = false;
      caixa.querySelector("button").addEventListener("click", function () {
        caixa.hidden = true;
        try { localStorage.setItem("ipe-site-lingua", atual); } catch (e) { /* sem armazenamento */ }
      });
      caixa.querySelector("a").addEventListener("click", function () {
        try { localStorage.setItem("ipe-site-lingua", nav); } catch (e) { /* sem armazenamento */ }
      });
    }
    document.querySelectorAll(".linguas a").forEach(function (a) {
      a.addEventListener("click", function () {
        try { localStorage.setItem("ipe-site-lingua", a.getAttribute("lang")); } catch (e) { /* idem */ }
      });
    });
  } catch (e) { /* sem armazenamento: sem sugestão */ }
})();
