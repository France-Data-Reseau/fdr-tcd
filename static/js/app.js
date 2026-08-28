// Scripts communs (externalisés de base.html v1 — comportement identique).
// CSP : aucun script inline dans les templates.

// Anti double-soumission : désactive les boutons submit au premier envoi.
document.addEventListener('submit', function (e) {
    var form = e.target;
    var btns = form.querySelectorAll('button[type="submit"]');
    btns.forEach(function (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.6';
    });
});
