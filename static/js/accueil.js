// Recherche de collectivités (externalisé d'accueil.html v1 — comportement identique).
var searchInput = document.getElementById('search');
var items = document.querySelectorAll('#coll-list li');
var noResults = document.getElementById('no-results');

searchInput.addEventListener('input', function () {
    var query = this.value.toLowerCase().trim();
    var visibleCount = 0;
    items.forEach(function (item) {
        var nom = item.getAttribute('data-nom');
        if (!query || nom.indexOf(query) !== -1) {
            item.classList.remove('hidden');
            visibleCount++;
        } else {
            item.classList.add('hidden');
        }
    });
    if (query && visibleCount === 0) {
        noResults.classList.add('visible');
    } else {
        noResults.classList.remove('visible');
    }
});

searchInput.focus();
