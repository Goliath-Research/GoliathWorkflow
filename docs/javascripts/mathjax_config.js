window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true
  },
  options: {
    skipHtmlTags: ["script", "noscript", "style", "textarea", "pre"],
    ignoreHtmlClass: "tex2jax_ignore",
    processHtmlClass: "arithmatex"
  }
};

function typesetMath() {
  if (window.MathJax && window.MathJax.typesetPromise) {
    window.MathJax.typesetPromise();
  }
}
if (typeof document$ !== "undefined") {
  document$.subscribe(typesetMath);
} else {
  document.addEventListener("DOMContentLoaded", typesetMath);
}
