// Filtre des cas d'usage par thème (externalisé de cas_usage.html v1 —
// comportement identique, le thème pré-sélectionné vient d'un data-attribute).
function filterByTheme(theme) {
    var groups = document.querySelectorAll('.cas-usage-group');
    groups.forEach(function (g) {
        if (!theme || g.getAttribute('data-theme') === theme) {
            g.style.display = 'block';
        } else {
            g.style.display = 'none';
        }
    });
}

var themeFilter = document.getElementById('theme_filter');
themeFilter.addEventListener('change', function () {
    filterByTheme(this.value);
});

var selectedTheme = themeFilter.getAttribute('data-selected-theme');
if (selectedTheme) {
    filterByTheme(selectedTheme);
}
