// Page de restitution (externalisé de restitution.html v1 — comportement
// identique). Seule adaptation : USER est lu depuis les data-attributes de
// #main-content (plus d'interpolation Jinja dans le JS — CSP stricte).
(function() {
    /* ---------- Palette ---------- */
    var PIE_COLORS = ['#43bfb5','#bed630','#339e95','#e8a838','#5b8def','#e06070','#9dd8d3','#a8bf2a','#7a6fbe','#f0b86e','#64747d','#c5ccd1'];
    var AVANCEMENT_COLORS = {
        'En réflexion':'#e8a838','Réflexion':'#e8a838',
        'En cours':'#43bfb5','En cours de déploiement':'#43bfb5','Déploiement':'#43bfb5',
        'Opérationnel':'#bed630','Terminé':'#bed630',
        'Abandonné':'#c5ccd1','Suspendu':'#c5ccd1'
    };

    /* ---------- Emojis cas d'usage ---------- */
    var CAS_EMOJI = {
        'eclairage':'💡','lumiere':'💡','eau':'💧','hydro':'💧',
        'mobil':'🚗','transport':'🚌','vehicul':'🚗',
        'energie':'⚡','electri':'⚡',
        'dechet':'♻️','tri':'♻️','ordure':'♻️',
        'batiment':'🏢','immobil':'🏢',
        'securit':'🔒','surete':'🔒','videop':'📹',
        'numerique':'💻','digital':'💻','fibre':'💻',
        'capteur':'📡','iot':'📡','objet':'📡',
        'donnee':'📊','data':'📊','open':'📊',
        'smart':'📱','ville':'🏙️','urbain':'🏙️',
        'environnement':'🌿','biodiver':'🌿',
        'climat':'🌡️','meteo':'🌡️',
        'stationnement':'🅿️','parking':'🅿️',
        'reseau':'🌐','telecom':'📶','infrastr':'🌐',
        'voirie':'🛣️','route':'🛣️',
        'agri':'🌾','agricul':'🌾',
        'sante':'🏥','soin':'🏥',
        'touris':'🏖️','culture':'🎭',
        'educa':'🎓','ecole':'🎓',
        'gestion':'📋','pilotage':'📋'
    };
    function getCasEmoji(name) {
        var lower = (name || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        for (var key in CAS_EMOJI) { if (lower.indexOf(key) !== -1) return CAS_EMOJI[key]; }
        return '📋';
    }

    /* ---------- State ---------- */
    var mainContent = document.getElementById('main-content');
    var USER = {
        droits: mainContent.dataset.droits || '',
        collectivite_id: parseInt(mainContent.dataset.collectiviteId || '0', 10) || 0
    };
    var allData = null, map = null, markersLayer = null;
    var statutColors = {};
    var collMiniMap = null;
    var avancementSteps = [''];
    var FILTER_IDS = ['f-couverture','f-statut','f-domaine','f-connectivite'];

    /* ---------- Onglets ---------- */
    document.querySelectorAll('.tab-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
            btn.classList.add('active');
            document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
            if (btn.dataset.tab === 'general' && map) setTimeout(function() { map.invalidateSize(); }, 100);
            if (btn.dataset.tab === 'ma-collectivite' && allData) initMaCollectivite();
        });
    });

    /* ---------- Carte ---------- */
    var TARGET_SCALE = 32000000;      // échelle cartographique cible : 1:32 000 000
    var FRANCE_CENTER = [46.7, 2.4];
    // Zoom Web Mercator donnant l'échelle voulue à une latitude donnée (96 dpi)
    function zoomForScale(scale, lat) {
        var resVoulue = scale * 0.00026458333; // m/px (1 px = 0.264583 mm à 96 dpi)
        var resZoom0 = 156543.03392 * Math.cos(lat * Math.PI / 180);
        return Math.log2(resZoom0 / resVoulue);
    }
    function applyFranceScale() {
        map.setView(FRANCE_CENTER, zoomForScale(TARGET_SCALE, FRANCE_CENTER[0]), { animate: false });
    }
    function initMap() {
        // zoomSnap:0 → autorise un zoom fractionnaire (échelle précise)
        map = L.map('map', { zoomSnap: 0, zoomDelta: 0.5 });
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap', maxZoom: 18
        }).addTo(map);
        L.control.scale({ metric: true, imperial: false, maxWidth: 150 }).addTo(map);
        markersLayer = L.layerGroup().addTo(map);
        applyFranceScale();
    }

    /* ---------- Chargement ---------- */
    async function loadData() {
        try {
            var resp = await fetch('/api/cartographie/donnees');
            allData = await resp.json();
            document.getElementById('loading-overlay').style.display = 'none';
            document.getElementById('main-content').style.display = '';
            (allData.filtres.statuts || []).forEach(function(s, i) {
                statutColors[s] = PIE_COLORS[i % PIE_COLORS.length];
            });
            initFilters();
            applyFilters();
            setTimeout(function() { map.invalidateSize(); }, 150);
        } catch(e) {
            document.getElementById('loading-overlay').innerHTML =
                '<p style="color:#dc2626;font-size:1.1rem;">Erreur lors du chargement des données.</p>';
        }
    }

    /* ---------- Filtres ---------- */
    function initFilters() {
        var f = allData.filtres;
        populateSelect('f-couverture', f.couvertures);
        populateSelect('f-statut', f.statuts);
        populateSelect('f-domaine', f.domaines);
        populateSelect('f-connectivite', f.connectivites);

        /* Slider avancement */
        avancementSteps = [''].concat(f.avancements || []);
        var slider = document.getElementById('av-slider');
        slider.max = avancementSteps.length - 1;
        slider.value = 0;
        updateSliderLabel();
        slider.addEventListener('input', function() {
            updateSliderLabel();
            applyFilters();
        });

        /* Cas d'usage checkboxes */
        var checks = document.getElementById('cas-usage-checks');
        var casUsages = f.cas_usages || [];
        checks.innerHTML = '';
        casUsages.forEach(function(cu) {
            var lbl = document.createElement('label');
            lbl.className = 'cas-check-item';
            lbl.innerHTML = '<input type="checkbox" value="' + esc(cu) + '"><span class="cas-emoji">' + getCasEmoji(cu) + '</span><span>' + esc(cu) + '</span>';
            lbl.querySelector('input').addEventListener('change', applyFilters);
            checks.appendChild(lbl);
        });
    }

    function updateSliderLabel() {
        var slider = document.getElementById('av-slider');
        var label = document.getElementById('av-slider-label');
        var idx = parseInt(slider.value);
        label.textContent = avancementSteps[idx] || 'Tous';
        var color = AVANCEMENT_COLORS[avancementSteps[idx]] || 'var(--gray-500)';
        label.style.color = idx > 0 ? color : '';
        label.style.fontWeight = idx > 0 ? '700' : '';
    }

    function populateSelect(id, values) {
        var sel = document.getElementById(id);
        var cur = sel.value;
        while (sel.options.length > 1) sel.remove(1);
        values.forEach(function(v) {
            var opt = document.createElement('option');
            opt.value = v; opt.textContent = v;
            sel.appendChild(opt);
        });
        sel.value = cur;
    }

    FILTER_IDS.forEach(function(id) {
        document.getElementById(id).addEventListener('change', applyFilters);
    });

    document.getElementById('reset-filters').addEventListener('click', function() {
        FILTER_IDS.forEach(function(id) { document.getElementById(id).value = ''; });
        document.getElementById('av-slider').value = 0;
        updateSliderLabel();
        document.querySelectorAll('#cas-usage-checks input').forEach(function(cb) { cb.checked = false; });
        applyFilters();
    });

    function applyFilters() {
        if (!allData) return;
        var fCouv = document.getElementById('f-couverture').value;
        var fStat = document.getElementById('f-statut').value;
        var fDom  = document.getElementById('f-domaine').value;
        var fConn = document.getElementById('f-connectivite').value;
        var fAv   = avancementSteps[parseInt(document.getElementById('av-slider').value)] || '';
        var checkedCas = [];
        document.querySelectorAll('#cas-usage-checks input:checked').forEach(function(cb) {
            checkedCas.push(cb.value);
        });

        var filtered = [];
        allData.collectivites.forEach(function(c) {
            if (fCouv && c.couverture !== fCouv) return;
            if (fStat && c.statut !== fStat) return;

            var projets = c.projets;
            if (fDom || fConn || fAv || checkedCas.length) {
                projets = projets.filter(function(p) {
                    if (fDom && p.domaine.indexOf(fDom) === -1) return false;
                    if (fConn && p.connectivite.indexOf(fConn) === -1) return false;
                    if (fAv && p.avancement !== fAv) return false;
                    if (checkedCas.length) {
                        var ok = p.cas_usages.some(function(cu) {
                            var nom = typeof cu === 'object' ? cu.nom : cu;
                            return checkedCas.indexOf(nom) !== -1;
                        });
                        if (!ok) return false;
                    }
                    return true;
                });
                if (projets.length === 0) return;
            }

            filtered.push({
                id: c.id, nom: c.nom, statut: c.statut, couverture: c.couverture,
                dep: c.dep, reg: c.reg, lat: c.lat, lng: c.lng,
                adresse: c.adresse, siren: c.siren, site_web: c.site_web,
                nb_projets: projets.length, projets: projets
            });
        });

        updateStats(filtered);
        updateMap(filtered);
        updateCharts(filtered);
        updateProjetsList(filtered);
    }

    /* ---------- Filtrer par collectivité (clic carte) ---------- */
    function filterByCollectivite(collName) {
        FILTER_IDS.forEach(function(id) { document.getElementById(id).value = ''; });
        document.getElementById('av-slider').value = 0;
        updateSliderLabel();
        document.querySelectorAll('#cas-usage-checks input').forEach(function(cb) { cb.checked = false; });

        if (!allData) return;
        var filtered = allData.collectivites.filter(function(c) { return c.nom === collName; });
        filtered = filtered.map(function(c) {
            return {
                id: c.id, nom: c.nom, statut: c.statut, couverture: c.couverture,
                dep: c.dep, reg: c.reg, lat: c.lat, lng: c.lng,
                adresse: c.adresse, siren: c.siren, site_web: c.site_web,
                url_logo: c.url_logo,
                nb_projets: c.projets.length, projets: c.projets
            };
        });
        updateStats(filtered);
        updateCharts(filtered);
        updateProjetsList(filtered);

        var card = document.getElementById('projets-list-card');
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /* ---------- Modale projet ---------- */
    function openProjetModal(projetId) {
        if (!allData) return;
        var projet = null, coll = null;
        allData.collectivites.forEach(function(c) {
            c.projets.forEach(function(p) {
                if (p.id === projetId && !projet) { projet = p; coll = c; }
            });
        });
        if (!projet) return;

        var h = '';
        /* Header */
        h += '<div class="modal-header-row">';
        if (coll.url_logo) h += '<img src="' + esc(coll.url_logo) + '" alt="" class="modal-coll-logo">';
        h += '<div class="modal-header-text">';
        h += '<h2 class="modal-title">' + esc(projet.nom) + '</h2>';
        h += '<span class="modal-subtitle">' + esc(coll.nom);
        if (coll.dep) h += ' — ' + esc(coll.dep);
        h += '</span>';
        h += '</div>';
        if (projet.avancement) h += '<span class="badge modal-badge">' + esc(projet.avancement) + '</span>';
        h += '</div>';

        /* Infos */
        if (projet.description) h += '<p class="modal-desc">' + esc(projet.description) + '</p>';

        h += '<div class="modal-meta-grid">';
        if (projet.echelle) h += '<div class="modal-meta-item"><span class="modal-meta-label">Échelle</span><span>' + esc(projet.echelle) + '</span></div>';
        if (projet.connectivite && projet.connectivite.length) h += '<div class="modal-meta-item"><span class="modal-meta-label">Connectivité</span><span>' + projet.connectivite.map(esc).join(', ') + '</span></div>';
        if (coll.couverture) h += '<div class="modal-meta-item"><span class="modal-meta-label">Couverture</span><span>' + esc(coll.couverture) + '</span></div>';
        if (coll.statut) h += '<div class="modal-meta-item"><span class="modal-meta-label">Type</span><span>' + esc(coll.statut) + '</span></div>';
        h += '</div>';

        /* Domaines */
        if (projet.domaine && projet.domaine.length) {
            h += '<div class="modal-section"><span class="modal-section-title">Thèmes</span>';
            h += '<div class="domain-chips">';
            projet.domaine.forEach(function(d) { h += '<span class="domain-chip">' + esc(d) + '</span>'; });
            h += '</div></div>';
        }

        /* Cas d'usage */
        if (projet.cas_usages && projet.cas_usages.length) {
            h += '<div class="modal-section"><span class="modal-section-title">Cas d\'usage</span>';
            h += '<div class="modal-pills">';
            projet.cas_usages.forEach(function(cu) {
                var nom = typeof cu === 'object' ? cu.nom : cu;
                if (nom) h += '<span class="cas-usage-pill">' + getCasEmoji(nom) + ' ' + esc(nom) + '</span>';
            });
            h += '</div></div>';
        }

        /* Partenaires */
        if (projet.partenaires && projet.partenaires.length) {
            h += '<div class="modal-section"><span class="modal-section-title">Partenaires</span><ul class="modal-list">';
            projet.partenaires.forEach(function(pa) {
                h += '<li>' + esc(pa.nom || '');
                if (pa.role) h += ' <span class="modal-role">(' + esc(typeof pa.role === 'string' ? pa.role : '') + ')</span>';
                h += '</li>';
            });
            h += '</ul></div>';
        }

        /* Programmes */
        if (projet.programmes && projet.programmes.length) {
            h += '<div class="modal-section"><span class="modal-section-title">Programmes</span><ul class="modal-list">';
            projet.programmes.forEach(function(pr) { h += '<li>' + esc(pr.nom || '') + '</li>'; });
            h += '</ul></div>';
        }

        /* Documents */
        if (projet.documents && projet.documents.length) {
            h += '<div class="modal-section"><span class="modal-section-title">Documents</span><ul class="modal-list">';
            projet.documents.forEach(function(d) {
                h += '<li>' + esc(d.titre || '');
                if (d.type) h += ' <span class="modal-role">(' + esc(d.type) + ')</span>';
                h += '</li>';
            });
            h += '</ul></div>';
        }

        document.getElementById('modal-body').innerHTML = h;
        document.getElementById('projet-modal').style.display = 'flex';
    }

    function openCollProjetsModal(collName) {
        if (!allData) return;
        var coll = allData.collectivites.find(function(c) { return c.nom === collName; });
        if (!coll || !coll.projets.length) return;
        if (coll.projets.length === 1) { openProjetModal(coll.projets[0].id); return; }

        var h = '<div class="modal-header-row">';
        if (coll.url_logo) h += '<img src="' + esc(coll.url_logo) + '" alt="" class="modal-coll-logo">';
        h += '<div class="modal-header-text">';
        h += '<h2 class="modal-title">' + esc(coll.nom) + '</h2>';
        h += '<span class="modal-subtitle">' + coll.projets.length + ' projet(s)';
        if (coll.dep) h += ' — ' + esc(coll.dep);
        h += '</span></div></div>';

        h += '<div class="modal-projets-list">';
        coll.projets.forEach(function(p) {
            h += '<a href="#" class="modal-projet-row" data-pid="' + p.id + '">';
            h += '<strong>' + esc(p.nom) + '</strong>';
            var tags = [];
            if (p.avancement) tags.push(p.avancement);
            if (p.domaine && p.domaine.length) tags = tags.concat(p.domaine);
            if (tags.length) {
                h += '<span class="modal-projet-tags">';
                tags.forEach(function(t) { h += '<span class="domain-chip">' + esc(t) + '</span>'; });
                h += '</span>';
            }
            h += '</a>';
        });
        h += '</div>';

        document.getElementById('modal-body').innerHTML = h;
        document.getElementById('projet-modal').style.display = 'flex';

        document.querySelectorAll('.modal-projet-row').forEach(function(el) {
            el.addEventListener('click', function(e) {
                e.preventDefault();
                openProjetModal(parseInt(el.dataset.pid));
            });
        });
    }

    /* Fermer la modale */
    document.getElementById('modal-close').addEventListener('click', function() {
        document.getElementById('projet-modal').style.display = 'none';
    });
    document.getElementById('projet-modal').addEventListener('click', function(e) {
        if (e.target === this) this.style.display = 'none';
    });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') document.getElementById('projet-modal').style.display = 'none';
    });

    /* ---------- Stats ---------- */
    function updateStats(filtered) {
        var nbProjets = 0, casSet = new Set(), seenP = new Set();
        filtered.forEach(function(c) {
            c.projets.forEach(function(p) {
                if (!seenP.has(p.id)) {
                    seenP.add(p.id); nbProjets++;
                    p.cas_usages.forEach(function(cu) {
                        var nom = typeof cu === 'object' ? cu.nom : cu;
                        if (nom) casSet.add(nom);
                    });
                }
            });
        });
        document.getElementById('s-collectivites').textContent = filtered.length;
        document.getElementById('s-projets').textContent = nbProjets;
        document.getElementById('s-cas-usages').textContent = casSet.size;
    }

    /* ---------- Carte (hover + couleurs par type + clic filtre) ---------- */
    function updateMap(filtered) {
        markersLayer.clearLayers();
        var bounds = [];
        filtered.forEach(function(c) {
            // N'afficher que les collectivités reliées à au moins un projet
            if (c.lat && c.lng && c.nb_projets > 0) {
                var color = statutColors[c.statut] || '#43bfb5';
                var tooltipContent = '<strong>' + esc(c.nom) + '</strong><br>' +
                    (c.statut ? esc(c.statut) + '<br>' : '') +
                    c.nb_projets + ' projet(s)';

                var marker = L.circleMarker([c.lat, c.lng], {
                    radius: Math.min(6 + c.nb_projets * 2, 18),
                    fillColor: color, color: color,
                    weight: 2, opacity: 1, fillOpacity: 0.75
                });
                marker.bindTooltip(tooltipContent, { direction: 'top', offset: [0, -8] });
                (function(collData) {
                    marker.on('click', function() {
                        openCollProjetsModal(collData.nom);
                    });
                })(c);
                markersLayer.addLayer(marker);
                bounds.push([c.lat, c.lng]);
            }
        });
        // Cadrage : ne tenir compte que des points métropolitains, sinon les
        // collectivités d'outre-mer (Réunion, Antilles, Guyane…) étireraient la
        // vue jusqu'à centrer la carte au milieu de l'Atlantique / l'Afrique.
        // Les marqueurs DOM-TOM restent placés (accessibles en dézoomant).
        // Vue à échelle fixe (1:32M) centrée sur la France — voir initMap().
        // On ne recadre pas sur les données (l'échelle resterait constante).
        updateMapLegend();
    }

    function updateMapLegend() {
        var el = document.getElementById('map-legend-bar');
        var statuts = Object.keys(statutColors);
        if (!statuts.length) { el.innerHTML = ''; return; }
        var html = '';
        statuts.forEach(function(s) {
            html += '<span class="map-legend-item"><span class="map-legend-dot" style="background:' + statutColors[s] + '"></span>' + esc(s) + '</span>';
        });
        el.innerHTML = html;
    }

    /* ---------- Graphiques ---------- */
    function updateCharts(filtered) {
        var seenP = new Set();
        var parConn = {}, parAv = {}, parDom = {}, parStatut = {};
        filtered.forEach(function(c) {
            parStatut[c.statut || 'Non défini'] = (parStatut[c.statut || 'Non défini'] || 0) + 1;
            c.projets.forEach(function(p) {
                if (seenP.has(p.id)) return;
                seenP.add(p.id);
                p.connectivite.forEach(function(v) { parConn[v] = (parConn[v] || 0) + 1; });
                if (p.avancement) parAv[p.avancement] = (parAv[p.avancement] || 0) + 1;
                p.domaine.forEach(function(v) { parDom[v] = (parDom[v] || 0) + 1; });
            });
        });
        renderDonut('pie-connectivite', 'legend-connectivite', parConn);
        renderDonut('pie-domaine', 'legend-domaine', parDom);
        renderDonut('pie-statut', 'legend-statut', parStatut);
        renderDonut('pie-avancement', 'legend-avancement', parAv, AVANCEMENT_COLORS);
    }

    /* ---------- Donuts ---------- */
    function renderDonut(pieId, legendId, data, colorMap) {
        var pieEl = document.getElementById(pieId);
        var legEl = document.getElementById(legendId);
        var entries = Object.entries(data).sort(function(a, b) { return b[1] - a[1]; });
        var total = entries.reduce(function(s, e) { return s + e[1]; }, 0);

        if (!total) {
            pieEl.style.background = 'var(--gray-100)';
            pieEl.innerHTML = '<span class="donut-center-text">0</span>';
            legEl.innerHTML = '<span class="empty" style="font-size:0.8rem">Aucune donnée</span>';
            return;
        }

        var gradParts = [], cumul = 0, segments = [];
        entries.forEach(function(e, i) {
            var pct = (e[1] / total) * 100;
            var color = (colorMap && colorMap[e[0]]) ? colorMap[e[0]] : PIE_COLORS[i % PIE_COLORS.length];
            gradParts.push(color + ' ' + cumul.toFixed(1) + '% ' + (cumul + pct).toFixed(1) + '%');
            segments.push({ pct: pct, cumul: cumul });
            cumul += pct;
        });
        pieEl.style.background = 'conic-gradient(' + gradParts.join(', ') + ')';

        var labelsHtml = '<span class="donut-center-text">' + total + '</span>';
        segments.forEach(function(seg) {
            if (seg.pct >= 10) {
                var midDeg = ((seg.cumul + seg.pct / 2) / 100) * 360 - 90;
                var rad = midDeg * Math.PI / 180;
                var cx = 50 + 38 * Math.cos(rad);
                var cy = 50 + 38 * Math.sin(rad);
                labelsHtml += '<span class="donut-pct" style="left:' + cx.toFixed(1) + '%;top:' + cy.toFixed(1) + '%">' + Math.round(seg.pct) + '%</span>';
            }
        });
        pieEl.innerHTML = labelsHtml;

        var html = '';
        entries.forEach(function(e, i) {
            var pct = Math.round((e[1] / total) * 100);
            var color = (colorMap && colorMap[e[0]]) ? colorMap[e[0]] : PIE_COLORS[i % PIE_COLORS.length];
            html += '<div class="pie-legend-item"><span class="pie-dot" style="background:' + color + '"></span>' +
                '<span class="pie-legend-label">' + esc(e[0]) + '</span>' +
                '<span class="pie-legend-val">' + e[1] + ' (' + pct + '%)</span></div>';
        });
        legEl.innerHTML = html;
    }

    /* ---------- Liste des projets ---------- */
    function updateProjetsList(filtered) {
        var tbody = document.getElementById('projets-table-body');
        var emptyMsg = document.getElementById('projets-list-empty');

        var rows = [], seenP = new Set();
        filtered.forEach(function(c) {
            c.projets.forEach(function(p) {
                if (seenP.has(p.id)) return;
                seenP.add(p.id);
                var casNames = p.cas_usages.map(function(cu) {
                    return typeof cu === 'object' ? cu.nom : cu;
                }).filter(Boolean);
                rows.push({
                    id: p.id,
                    nom: p.nom,
                    collectivite: c.nom,
                    dep: c.dep || '',
                    connectivite: p.connectivite.join(', '),
                    couverture: c.couverture || '',
                    cas_usages: casNames
                });
            });
        });

        if (!rows.length) {
            tbody.innerHTML = '';
            emptyMsg.style.display = '';
            return;
        }
        emptyMsg.style.display = 'none';

        var html = '';
        rows.forEach(function(r) {
            var casHtml = r.cas_usages.map(function(cu) {
                return '<span class="cas-usage-pill">' + getCasEmoji(cu) + ' ' + esc(cu) + '</span>';
            }).join('');
            html += '<tr>' +
                '<td class="td-nom"><a href="#" class="projet-link" data-pid="' + r.id + '">' + esc(r.nom) + '</a></td>' +
                '<td class="td-collectivite">' + esc(r.collectivite) + '</td>' +
                '<td>' + esc(r.dep) + '</td>' +
                '<td>' + esc(r.connectivite) + '</td>' +
                '<td>' + esc(r.couverture) + '</td>' +
                '<td class="td-cas-usage">' + (casHtml || '-') + '</td>' +
                '</tr>';
        });
        tbody.innerHTML = html;

        /* Clic sur nom de projet → modale */
        tbody.querySelectorAll('.projet-link').forEach(function(el) {
            el.addEventListener('click', function(e) {
                e.preventDefault();
                openProjetModal(parseInt(el.dataset.pid));
            });
        });
    }

    function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    /* ---------- Ma Collectivité ---------- */
    function initMaCollectivite() {
        if (!allData) return;
        var collId = USER.collectivite_id;
        if (USER.droits === 'Administrateur') {
            var sel = document.getElementById('select-ma-coll');
            if (!sel.dataset.bound) {
                sel.addEventListener('change', function() { showCollDetail(parseInt(sel.value) || 0); });
                sel.dataset.bound = '1';
            }
            if (sel.value) showCollDetail(parseInt(sel.value));
        } else if (collId) {
            showCollDetail(collId);
        } else {
            document.getElementById('ma-coll-content').innerHTML = '<div class="empty">Aucune collectivité associée à votre compte.</div>';
        }
    }

    function showCollDetail(collId) {
        if (collMiniMap) { collMiniMap.remove(); collMiniMap = null; }
        var el = document.getElementById('ma-coll-content');
        if (!collId) { el.innerHTML = '<div class="empty">Sélectionnez une collectivité.</div>'; return; }
        var coll = allData.collectivites.find(function(c) { return c.id === collId; });
        if (!coll) { el.innerHTML = '<div class="empty">Collectivité introuvable.</div>'; return; }

        var h = '<div class="card">';
        h += '<div class="coll-detail-header-row">';
        if (coll.url_logo) {
            h += '<img src="' + esc(coll.url_logo) + '" alt="" class="coll-logo">';
        }
        h += '<div class="coll-detail-header-text">';
        h += '<h2 style="margin:0;padding:0;border:none;">' + esc(coll.nom) + '</h2>';
        h += '</div>';
        if (USER.droits === 'Administrateur' || USER.droits === 'Editeur') {
            h += '<a href="/collectivite/' + collId + '" class="btn btn-primary btn-sm">Mettre à jour mes données</a>';
        }
        h += '</div>';

        h += '<div class="coll-info-grid">';
        [['Type', coll.statut],['Couverture', coll.couverture],['SIREN', coll.siren],
         ['Département', coll.dep],['Région', coll.reg],['Adresse', coll.adresse]].forEach(function(item) {
            if (item[1]) {
                h += '<div class="coll-info-item"><span class="coll-info-label">' + item[0] + '</span>';
                h += '<span class="coll-info-value">' + esc(String(item[1])) + '</span></div>';
            }
        });
        if (coll.site_web) {
            h += '<div class="coll-info-item"><span class="coll-info-label">Site web</span>';
            h += '<a href="' + esc(coll.site_web) + '" target="_blank" class="coll-info-value" style="color:var(--fnccr-teal)">' + esc(coll.site_web) + '</a></div>';
        }
        h += '</div>';

        if (coll.lat && coll.lng) h += '<div id="coll-mini-map" class="mini-map"></div>';

        if (!coll.projets.length) {
            h += '<p class="empty">Aucun projet enregistré.</p>';
        } else {
            h += '<h3 style="margin-top:1.25rem">' + coll.projets.length + ' projet(s)</h3>';
            h += '<div class="projets-grid">';
            coll.projets.forEach(function(p) {
                h += '<div class="projet-detail-card">';
                h += '<div class="projet-detail-header"><strong>' + esc(p.nom) + '</strong>';
                if (p.avancement) h += '<span class="badge">' + esc(p.avancement) + '</span>';
                h += '</div>';
                if (p.domaine && p.domaine.length) {
                    h += '<div class="domain-chips">';
                    p.domaine.forEach(function(d) { h += '<span class="domain-chip">' + esc(d) + '</span>'; });
                    h += '</div>';
                }
                if (p.description) h += '<p class="projet-desc">' + esc(p.description) + '</p>';
                var meta = [];
                if (p.echelle) meta.push('Échelle : ' + p.echelle);
                if (p.connectivite.length) meta.push('Connectivité : ' + p.connectivite.join(', '));
                if (meta.length) h += '<div class="projet-meta">' + meta.map(esc).join(' &middot; ') + '</div>';
                [['cas_usages','Cas d\'usage','nom'],['partenaires','Partenaires','nom'],
                 ['programmes','Programmes','nom'],['documents','Documents','titre']].forEach(function(cfg) {
                    var items = p[cfg[0]];
                    if (items && items.length) {
                        h += '<div class="sous-section"><span class="sous-title">' + cfg[1] + '</span><ul class="sous-list">';
                        items.forEach(function(it) {
                            var label = typeof it === 'object' ? (it[cfg[2]] || it.nom || '') : it;
                            h += '<li>' + esc(label) + '</li>';
                        });
                        h += '</ul></div>';
                    }
                });
                h += '</div>';
            });
            h += '</div>';
        }
        h += '</div>';
        el.innerHTML = h;

        if (coll.lat && coll.lng) {
            setTimeout(function() {
                var mapEl = document.getElementById('coll-mini-map');
                if (!mapEl) return;
                collMiniMap = L.map('coll-mini-map', {
                    zoomControl: false, attributionControl: false,
                    dragging: false, scrollWheelZoom: false,
                    doubleClickZoom: false, touchZoom: false
                }).setView([coll.lat, coll.lng], 12);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18 }).addTo(collMiniMap);
                L.marker([coll.lat, coll.lng]).addTo(collMiniMap);
            }, 100);
        }
    }

    /* ---------- Init ---------- */
    initMap();
    loadData();
})();
