document.addEventListener("DOMContentLoaded", () => {
    // --- State ---
    let activeTab = "matches";
    let activeStatusFilter = "new";
    let config = null;
    let venues = [];
    let concerts = [];

    // --- DOM Elements ---
    const navItems = document.querySelectorAll(".nav-item");
    const tabContents = document.querySelectorAll(".tab-content");
    const pageTitle = document.getElementById("page-title");
    const pageSubtitle = document.getElementById("page-subtitle");
    
    // Sync Button
    const btnSyncFeeds = document.getElementById("btn-sync-feeds");
    
    // Matches Tab
    const matchesGrid = document.getElementById("matches-grid");
    const matchesLoader = document.getElementById("matches-loader");
    const noMatches = document.getElementById("no-matches");
    const filterPills = document.querySelectorAll(".filter-pill");
    
    // Venues Tab
    const venuesTableBody = document.getElementById("venues-table-body");
    const btnAddVenue = document.getElementById("btn-add-venue");
    
    // Parser Tab
    const btnParseEmail = document.getElementById("btn-parse-email");
    const newsletterText = document.getElementById("newsletter-text");
    const parserLoader = document.getElementById("parser-loader");
    const parserResults = document.getElementById("parser-results");
    const parserResultsSummary = document.getElementById("parser-results-summary");
    const parserResultsGrid = document.getElementById("parser-results-grid");
    
    // Settings Tab
    const homeLat = document.getElementById("home-lat");
    const homeLon = document.getElementById("home-lon");
    const radiusSmall = document.getElementById("radius-small");
    const radiusMedium = document.getElementById("radius-medium");
    const radiusLarge = document.getElementById("radius-large");
    
    // Sleutels & SMTP inputs
    const geminiKey = document.getElementById("gemini-key");
    const spotifyId = document.getElementById("spotify-id");
    const spotifySecret = document.getElementById("spotify-secret");
    const spotifyRedirect = document.getElementById("spotify-redirect");
    const smtpServer = document.getElementById("smtp-server");
    const smtpPort = document.getElementById("smtp-port");
    const smtpUsername = document.getElementById("smtp-username");
    const smtpPassword = document.getElementById("smtp-password");
    const smtpFrom = document.getElementById("smtp-from");
    const smtpTo = document.getElementById("smtp-to");
    
    // IMAP inputs
    const imapServer = document.getElementById("imap-server");
    const imapPort = document.getElementById("imap-port");
    const imapUsername = document.getElementById("imap-username");
    const imapPassword = document.getElementById("imap-password");
    const imapEnabled = document.getElementById("imap-enabled");
    
    const btnSaveConfig = document.getElementById("btn-save-config");
    
    const spotifyConnTitle = document.getElementById("spotify-conn-title");
    const spotifyConnDesc = document.getElementById("spotify-conn-desc");
    const btnSpotifyConnect = document.getElementById("btn-spotify-connect");
    const btnSpotifySync = document.getElementById("btn-spotify-sync");
    const icsFeedUrlInput = document.getElementById("ics-feed-url");
    const btnCopyIcs = document.getElementById("btn-copy-ics");
    
    // Modal
    const venueModal = document.getElementById("venue-modal");
    const venueForm = document.getElementById("venue-form");
    const venueIdInput = document.getElementById("venue-id");
    const venueFormName = document.getElementById("venue-form-name");
    const venueFormCategory = document.getElementById("venue-form-category");
    const venueFormLat = document.getElementById("venue-form-lat");
    const venueFormLon = document.getElementById("venue-form-lon");
    const venueFormCity = document.getElementById("venue-form-city");
    const venueFormUrl = document.getElementById("venue-form-url");
    const venueFormAliases = document.getElementById("venue-form-aliases");
    const btnCloseModal = document.getElementById("btn-close-modal");
    const btnCancelVenue = document.getElementById("btn-cancel-venue");

    // Scrapers Tab & Modal elements
    const scrapersTableBody = document.getElementById("scrapers-table-body");
    const btnAddScraper = document.getElementById("btn-add-scraper");
    const modalScraper = document.getElementById("modal-scraper");
    const scraperForm = document.getElementById("scraper-form");
    const scraperIdInput = document.getElementById("scraper-id");
    const scraperModalTitle = document.getElementById("scraper-modal-title");
    const scraperFormName = document.getElementById("scraper-form-name");
    const scraperFormUrl = document.getElementById("scraper-form-url");
    const scraperFormEnabled = document.getElementById("scraper-form-enabled");
    const btnCloseScraperModal = document.getElementById("btn-close-scraper-modal");
    const btnCancelScraper = document.getElementById("btn-cancel-scraper");
    const btnSubmitScraper = document.getElementById("btn-submit-scraper");
    
    // Scraper Code Modal (reused for Venues)
    const modalScraperCode = document.getElementById("modal-scraper-code");
    const scraperCodeForm = document.getElementById("scraper-code-form");
    const scraperCodeTitle = document.getElementById("scraper-code-title");
    const scraperCodeId = document.getElementById("scraper-code-id");
    const scraperCodeName = document.getElementById("scraper-code-name");
    const scraperCodeUrl = document.getElementById("scraper-code-url");
    const scraperCodeEnabled = document.getElementById("scraper-code-enabled");
    const scraperCodeTextarea = document.getElementById("scraper-code-textarea");
    const btnCloseCodeModal = document.getElementById("btn-close-code-modal");
    const btnCancelCode = document.getElementById("btn-cancel-code");
    const btnHealScraperManual = document.getElementById("btn-heal-scraper-manual");

    // Dynamic ICS link setup
    icsFeedUrlInput.value = `${window.location.protocol}//${window.location.host}/feed.ics`;

    // --- Tab Switcher ---
    navItems.forEach(item => {
        item.addEventListener("click", () => {
            const tabName = item.getAttribute("data-tab");
            switchTab(tabName);
        });
    });

    function switchTab(tabName) {
        activeTab = tabName;
        
        // Update menu items
        navItems.forEach(item => {
            if (item.getAttribute("data-tab") === tabName) {
                item.classList.add("active");
            } else {
                item.classList.remove("active");
            }
        });
        
        // Update content panes
        tabContents.forEach(pane => {
            if (pane.id === `tab-${tabName}`) {
                pane.classList.add("active");
            } else {
                pane.classList.remove("active");
            }
        });
        
        // Update titles
        if (tabName === "matches") {
            pageTitle.innerText = "Aanbevelingen";
            pageSubtitle.innerText = "Jouw gepersonaliseerde concert agenda op basis van Spotify & Locatie";
            btnSyncFeeds.style.display = "inline-flex";
            loadConcerts();
        } else if (tabName === "venues") {
            pageTitle.innerText = "Podia & Zalen";
            pageSubtitle.innerText = "Overzicht van locaties en afstandsinstellingen";
            btnSyncFeeds.style.display = "none";
            loadVenues();
        } else if (tabName === "parser") {
            pageTitle.innerText = "Nieuwsbrief Parser";
            pageSubtitle.innerText = "Concertgegevens extraheren met Gemini AI";
            btnSyncFeeds.style.display = "none";
        } else if (tabName === "scrapers") {
            pageTitle.innerText = "Custom Scrapers";
            pageSubtitle.innerText = "Zelf-herstellende BeautifulSoup scrapers voor podium websites";
            btnSyncFeeds.style.display = "none";
            loadScrapers();
        } else if (tabName === "settings") {
            pageTitle.innerText = "Instellingen";
            pageSubtitle.innerText = "Beheer je thuislocatie, zoekstralen en Spotify-koppeling";
            btnSyncFeeds.style.display = "none";
            loadConfig();
            loadSpotifyStatus();
        }
    }

    // --- API Calls ---
    
    // Sync Feeds
    btnSyncFeeds.addEventListener("click", async () => {
        btnSyncFeeds.disabled = true;
        btnSyncFeeds.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Bezig met syncen...';
        
        try {
            const response = await fetch("/api/concerts/sync", { method: "POST" });
            if (response.ok) {
                alert("Synchronisatie is gestart op de achtergrond. Concerten laden zo meteen in.");
                setTimeout(() => {
                    loadConcerts();
                    btnSyncFeeds.disabled = false;
                    btnSyncFeeds.innerHTML = '<i class="fa-solid fa-rotate"></i> Sync Feeds';
                }, 2000);
            } else {
                alert("Fout bij het triggeren van de sync.");
                btnSyncFeeds.disabled = false;
                btnSyncFeeds.innerHTML = '<i class="fa-solid fa-rotate"></i> Sync Feeds';
            }
        } catch (err) {
            console.error("Sync error:", err);
            btnSyncFeeds.disabled = false;
            btnSyncFeeds.innerHTML = '<i class="fa-solid fa-rotate"></i> Sync Feeds';
        }
    });

    // Load Config
    async function loadConfig() {
        try {
            const res = await fetch("/api/config");
            config = await res.json();
            
            homeLat.value = config.home_latitude;
            homeLon.value = config.home_longitude;
            radiusSmall.value = config.radius_small;
            radiusMedium.value = config.radius_medium;
            radiusLarge.value = config.radius_large;
            
            // Keys
            geminiKey.value = config.gemini_api_key || "";
            spotifyId.value = config.spotify_client_id || "";
            spotifySecret.value = config.spotify_client_secret || "";
            spotifyRedirect.value = config.spotify_redirect_uri || "http://127.0.0.1:8080/callback";
            
            // SMTP
            smtpServer.value = config.smtp_server || "";
            smtpPort.value = config.smtp_port || 587;
            smtpUsername.value = config.smtp_username || "";
            smtpPassword.value = config.smtp_password || "";
            smtpFrom.value = config.smtp_from_email || "";
            smtpTo.value = config.smtp_to_email || "";
            
            // IMAP
            imapServer.value = config.imap_server || "";
            imapPort.value = config.imap_port || 993;
            imapUsername.value = config.imap_username || "";
            imapPassword.value = config.imap_password || "";
            imapEnabled.checked = config.imap_enabled || false;
        } catch (err) {
            console.error("Fout bij laden configuratie:", err);
        }
    }

    // Save Config
    btnSaveConfig.addEventListener("click", async () => {
        const payload = {
            home_latitude: parseFloat(homeLat.value),
            home_longitude: parseFloat(homeLon.value),
            radius_small: parseFloat(radiusSmall.value),
            radius_medium: parseFloat(radiusMedium.value),
            radius_large: parseFloat(radiusLarge.value),
            
            // Keys
            gemini_api_key: geminiKey.value.trim() || null,
            spotify_client_id: spotifyId.value.trim() || null,
            spotify_client_secret: spotifySecret.value.trim() || null,
            spotify_redirect_uri: spotifyRedirect.value.trim() || "http://127.0.0.1:8080/callback",
            
            // SMTP
            smtp_server: smtpServer.value.trim() || null,
            smtp_port: parseInt(smtpPort.value) || 587,
            smtp_username: smtpUsername.value.trim() || null,
            smtp_password: smtpPassword.value || null,
            smtp_from_email: smtpFrom.value.trim() || null,
            smtp_to_email: smtpTo.value.trim() || null,
            
            // IMAP
            imap_server: imapServer.value.trim() || null,
            imap_port: parseInt(imapPort.value) || 993,
            imap_username: imapUsername.value.trim() || null,
            imap_password: imapPassword.value || null,
            imap_enabled: imapEnabled.checked
        };
        
        try {
            const res = await fetch("/api/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                alert("Instellingen succesvol opgeslagen! Concert-scores worden opnieuw berekend.");
                loadConfig();
                loadSpotifyStatus(); // Spotify status herladen voor het geval ID/Secret zijn veranderd
            } else {
                alert("Fout bij opslaan instellingen.");
            }
        } catch (err) {
            console.error(err);
        }
    });


    // Load Spotify Status
    async function loadSpotifyStatus() {
        try {
            const res = await fetch("/api/spotify/status");
            const status = await res.json();
            
            if (status.connected) {
                spotifyConnTitle.innerHTML = '<i class="fa-solid fa-circle-check" style="color: var(--success);"></i> Spotify Gekoppeld';
                spotifyConnDesc.innerText = `Smaakprofiel actief: ${status.top_artists_count} top artiesten en ${status.cached_artists_count} cached genres.`;
                btnSpotifyConnect.style.display = "none";
                btnSpotifySync.style.display = "inline-flex";
            } else {
                spotifyConnTitle.innerHTML = '<i class="fa-solid fa-circle-xmark" style="color: var(--danger);"></i> Spotify Niet Gekoppeld';
                spotifyConnDesc.innerText = "Koppel je Spotify-account om concerten te matchen met je luistergedrag.";
                btnSpotifyConnect.style.display = "inline-flex";
                btnSpotifySync.style.display = "none";
                
                // Pas de login link aan om eventueel een dynamic redirect uri mee te sturen
                btnSpotifyConnect.href = `/login/spotify`;
            }
        } catch (err) {
            console.error(err);
        }
    }

    // Spotify Sync Preference
    btnSpotifySync.addEventListener("click", async () => {
        btnSpotifySync.disabled = true;
        btnSpotifySync.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Bezig...';
        try {
            const res = await fetch("/api/spotify/sync", { method: "POST" });
            const data = await res.json();
            if (res.ok) {
                alert(`Spotify smaakprofiel succesvol gesynchroniseerd! ${data.synced_artists} artiesten ingeladen.`);
                loadSpotifyStatus();
            } else {
                alert(`Fout bij synchroniseren: ${data.detail || "Onbekend"}`);
            }
        } catch (err) {
            console.error(err);
        } finally {
            btnSpotifySync.disabled = false;
            btnSpotifySync.innerHTML = '<i class="fa-solid fa-rotate"></i> Synchroniseer Smaak';
        }
    });

    // Load Venues
    async function loadVenues() {
        try {
            const res = await fetch("/api/venues");
            venues = await res.json();
            renderVenues();
        } catch (err) {
            console.error(err);
        }
    }

    function renderVenues() {
        venuesTableBody.innerHTML = "";
        venues.forEach(v => {
            const tr = document.createElement("tr");
            
            const website = v.url ? `<a href="${v.url}" target="_blank" style="color: var(--primary);"><i class="fa-solid fa-arrow-up-right-from-square"></i> Open</a>` : '<span class="text-dark">-</span>';
            
            // Scraper column & buttons
            let scraperCol = '<span class="text-dark">-</span>';
            let scraperButtons = '';
            if (v.scraper_url) {
                let statusBadge = '<span class="status-pill status-new" style="font-size: 11px; padding: 2px 6px;">Nooit</span>';
                if (v.scraper_last_status === "success") {
                    statusBadge = '<span class="status-pill status-interested" style="font-size: 11px; padding: 2px 6px;"><i class="fa-solid fa-check"></i> OK</span>';
                } else if (v.scraper_last_status === "failed") {
                    statusBadge = '<span class="status-pill status-ignored" style="font-size: 11px; padding: 2px 6px;" title="' + (v.scraper_error_log || '').replace(/"/g, '&quot;') + '"><i class="fa-solid fa-xmark"></i> Fail</span>';
                }
                
                // Toggle switch for Enabled
                const enabledToggle = `
                    <label class="switch" style="position: relative; display: inline-block; width: 40px; height: 20px; margin-right: 10px; vertical-align: middle;">
                        <input type="checkbox" class="scraper-toggle-enabled" data-id="${v.id}" ${v.scraper_enabled !== false ? 'checked' : ''} style="opacity: 0; width: 0; height: 0;">
                        <span class="slider round" style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: ${v.scraper_enabled !== false ? '#6366f1' : '#ccc'}; transition: .4s; border-radius: 20px;"></span>
                    </label>
                `;

                scraperCol = `
                    <div style="font-size: 12px; max-width: 300px; display: flex; align-items: center;">
                        ${enabledToggle}
                        <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            <a href="${v.scraper_url}" target="_blank" class="text-muted" style="text-decoration: underline;">${v.scraper_url}</a>
                            <div style="margin-top: 4px;">${statusBadge}</div>
                        </div>
                    </div>
                `;
                scraperButtons = `
                    <button class="btn btn-secondary btn-sm btn-run-scraper" data-id="${v.id}" title="Run Scraper" style="margin-right: 5px; padding: 4px 8px; background: rgba(99, 102, 241, 0.15); color: #818cf8;"><i class="fa-solid fa-play"></i> Run</button>
                    <button class="btn btn-secondary btn-sm btn-view-code" data-id="${v.id}" data-name="${v.name}" data-url="${v.scraper_url}" data-code="${(v.scraper_code || '').replace(/"/g, '&quot;')}" data-enabled="${v.scraper_enabled}" title="Bekijk BeautifulSoup Code" style="margin-right: 5px; padding: 4px 8px;"><i class="fa-solid fa-code"></i> Code</button>
                `;
            }
            
            tr.innerHTML = `
                <td style="font-weight: bold; color: #ffffff;">${v.name}</td>
                <td>${website}</td>
                <td>${scraperCol}</td>
                <td style="text-align: right; white-space: nowrap;">
                    ${scraperButtons}
                    <button class="btn btn-secondary btn-sm btn-edit-venue" data-id="${v.id}" style="margin-right: 5px;"><i class="fa-solid fa-pen"></i></button>
                    <button class="btn btn-danger btn-sm btn-delete-venue" data-id="${v.id}"><i class="fa-solid fa-trash"></i></button>
                </td>
            `;
            
            // Event Listeners
            tr.querySelector(".btn-edit-venue").addEventListener("click", () => openVenueModal(v));
            tr.querySelector(".btn-delete-venue").addEventListener("click", () => deleteVenue(v.id));
            
            if (v.scraper_url) {
                tr.querySelector(".scraper-toggle-enabled").addEventListener("change", async (e) => {
                    const id = e.target.getAttribute("data-id");
                    const enabled = e.target.checked;
                    await toggleVenueScraperEnabled(id, enabled);
                });
                
                tr.querySelector(".btn-run-scraper").addEventListener("click", async (e) => {
                    const btn = e.currentTarget;
                    btn.disabled = true;
                    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                    await runVenueScraper(v.id);
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-play"></i> Run';
                });
                
                tr.querySelector(".btn-view-code").addEventListener("click", () => {
                    scraperCodeId.value = v.id;
                    scraperCodeName.value = v.name;
                    scraperCodeUrl.value = v.scraper_url;
                    scraperCodeEnabled.checked = v.scraper_enabled !== false;
                    scraperCodeTitle.innerText = `Scraper Code: ${v.name}`;
                    scraperCodeTextarea.value = v.scraper_code || "";
                    modalScraperCode.classList.add("active");
                });
            }
            
            venuesTableBody.appendChild(tr);
        });
    }

    // Delete Venue
    async function deleteVenue(id) {
        if (!confirm("Weet je zeker dat je dit podium wilt verwijderen?")) return;
        try {
            const res = await fetch(`/api/venues/${id}`, { method: "DELETE" });
            if (res.ok) {
                if (activeTab === "venues") {
                    loadVenues();
                } else if (activeTab === "scrapers") {
                    loadScrapers();
                }
            } else {
                alert("Fout bij het verwijderen.");
            }
        } catch (err) {
            console.error(err);
        }
    }

    // Modal Controls for Venues
    btnAddVenue.addEventListener("click", () => openVenueModal());
    btnCloseModal.addEventListener("click", closeVenueModal);
    btnCancelVenue.addEventListener("click", closeVenueModal);
    
    function openVenueModal(venue = null) {
        if (venue) {
            document.getElementById("modal-title").innerText = "Podium Bewerken";
            venueIdInput.value = venue.id;
            venueFormName.value = venue.name;
            venueFormCategory.value = venue.category;
            venueFormLat.value = venue.latitude;
            venueFormLon.value = venue.longitude;
            venueFormCity.value = venue.city || "";
            venueFormUrl.value = venue.url || "";
            venueFormAliases.value = venue.aliases || "";
        } else {
            document.getElementById("modal-title").innerText = "Podium Toevoegen";
            venueIdInput.value = "";
            venueForm.reset();
            
            // Geen default coords prefillen in formulier zodat ze Stad kunnen gebruiken
            venueFormLat.value = "";
            venueFormLon.value = "";
            venueFormCity.value = "";
        }
        venueModal.classList.add("active");
    }
    
    function closeVenueModal() {
        venueModal.classList.remove("active");
    }

    // Save Venue (Modal Form Submit)
    venueForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = venueIdInput.value;
        const venue = id ? venues.find(v => v.id == id) : null;
        
        const payload = {
            name: venueFormName.value.trim(),
            category: venueFormCategory.value,
            latitude: venueFormLat.value ? parseFloat(venueFormLat.value) : null,
            longitude: venueFormLon.value ? parseFloat(venueFormLon.value) : null,
            city: venueFormCity.value.trim() || null,
            url: venueFormUrl.value.trim() || null,
            aliases: venueFormAliases.value.trim() || "",
            
            scraper_url: venue ? venue.scraper_url : null,
            scraper_enabled: venue ? (venue.scraper_enabled !== false) : true,
            scraper_code: venue ? venue.scraper_code : null
        };
        
        const url = id ? `/api/venues/${id}` : "/api/venues";
        const method = id ? "PUT" : "POST";
        
        try {
            const res = await fetch(url, {
                method: method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
             if (res.ok) {
                closeVenueModal();
                if (activeTab === "venues") {
                    loadVenues();
                } else if (activeTab === "scrapers") {
                    loadScrapers();
                }
            } else {
                const data = await res.json();
                alert(`Fout bij opslaan: ${data.detail || "Onbekend"}`);
            }
        } catch (err) {
            console.error(err);
        }
    });

    // --- Concerts Tab & Matches ---
    
    // Status Filter pills
    filterPills.forEach(pill => {
        pill.addEventListener("click", () => {
            filterPills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            activeStatusFilter = pill.getAttribute("data-status");
            loadConcerts();
        });
    });

    // Load Concerts
    async function loadConcerts() {
        matchesLoader.style.display = "flex";
        matchesGrid.style.display = "none";
        noMatches.style.display = "none";
        
        let url = "/api/concerts";
        if (activeStatusFilter !== "all") {
            url += `?status=${activeStatusFilter}`;
        }
        
        try {
            const res = await fetch(url);
            concerts = await res.json();
            renderConcerts();
        } catch (err) {
            console.error(err);
        } finally {
            matchesLoader.style.display = "none";
        }
    }

    function renderConcerts() {
        matchesGrid.innerHTML = "";
        
        if (concerts.length === 0) {
            matchesGrid.style.display = "none";
            noMatches.style.display = "block";
            return;
        }
        
        matchesGrid.style.display = "grid";
        noMatches.style.display = "none";
        
        concerts.forEach(c => {
            const card = document.createElement("div");
            card.className = "card";
            
            // Score Badge styling
            let scoreClass = "low";
            if (c.calculated_score >= 8.0) {
                scoreClass = "high";
            } else if (c.calculated_score >= 5.0) {
                scoreClass = "medium";
            }
            
            // Format data
            const dateObj = new Date(c.date);
            const dateStr = dateObj.toLocaleDateString("nl-NL", { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
            
            const priceStr = c.price ? `€${c.price.toFixed(2)}` : '<span class="text-dark">Onbekend</span>';
            const ticketSale = c.ticket_sale_start ? new Date(c.ticket_sale_start).toLocaleString("nl-NL", { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '<span class="text-dark">Onbekend</span>';
            
            // Status badges
            let statusPill = `<span class="status-badge ${c.status}">${c.status.toUpperCase()}</span>`;
            
            // Action Buttons based on current filter status
            let actionsHTML = "";
            if (c.status === "new") {
                actionsHTML = `
                    <button class="btn btn-success btn-sm btn-action" data-action="interested"><i class="fa-solid fa-calendar-check"></i> Ga</button>
                    <button class="btn btn-danger btn-sm btn-action" data-action="ignored"><i class="fa-solid fa-calendar-xmark"></i> Negeren</button>
                `;
            } else {
                actionsHTML = `
                    <button class="btn btn-secondary btn-sm btn-action" data-action="new"><i class="fa-solid fa-undo"></i> Zet Terug</button>
                    ${c.status !== "interested" ? `<button class="btn btn-success btn-sm btn-action" data-action="interested"><i class="fa-solid fa-calendar-check"></i> Ga</button>` : ""}
                    ${c.status !== "ignored" ? `<button class="btn btn-danger btn-sm btn-action" data-action="ignored"><i class="fa-solid fa-calendar-xmark"></i> Negeren</button>` : ""}
                `;
            }
            
            const ticketsBtn = c.url ? `<a href="${c.url}" target="_blank" class="btn btn-primary btn-sm"><i class="fa-solid fa-ticket"></i> Tickets</a>` : "";
            
            card.innerHTML = `
                <div class="card-header">
                    <h3 class="card-title">${c.artist}</h3>
                    <div class="score-badge ${scoreClass}">
                        <div style="font-size:10px; opacity:0.6; font-weight:500;">Match</div>
                        ${c.calculated_score.toFixed(1)}
                    </div>
                </div>
                <div class="card-body">
                    <div class="card-info-item">
                        <i class="fa-solid fa-map-pin"></i>
                        <span>${c.venue ? c.venue.name : "Onbekend"} (${c.venue ? c.venue.category.toUpperCase() : ""})</span>
                    </div>
                    <div class="card-info-item">
                        <i class="fa-solid fa-calendar"></i>
                        <span>${dateStr}</span>
                    </div>
                    <div class="card-info-item">
                        <i class="fa-solid fa-coins"></i>
                        <span>Ticket: ${priceStr}</span>
                    </div>
                    <div class="card-info-item">
                        <i class="fa-solid fa-clock"></i>
                        <span>Kaartverkoop: ${ticketSale}</span>
                    </div>
                    <div style="margin-top:5px; display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:11px; opacity:0.5;">Bron: ${c.source}</span>
                        ${statusPill}
                    </div>
                </div>
                <div class="card-footer">
                    ${actionsHTML}
                    <div style="margin-left: auto;">
                        ${ticketsBtn}
                    </div>
                </div>
            `;
            
            // Wire buttons
            card.querySelectorAll(".btn-action").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const action = btn.getAttribute("data-action");
                    await updateConcertStatus(c.id, action);
                });
            });
            
            matchesGrid.appendChild(card);
        });
    }

    async function updateConcertStatus(id, status) {
        try {
            const res = await fetch(`/api/concerts/${id}/status`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status: status })
            });
            if (res.ok) {
                // Herlaad concerten
                loadConcerts();
            } else {
                alert("Fout bij updaten concert status.");
            }
        } catch (err) {
            console.error(err);
        }
    }

    // --- Parser Tab (Gemini) ---
    btnParseEmail.addEventListener("click", async () => {
        const text = newsletterText.value.trim();
        if (!text) {
            alert("Plak eerst e-mail tekst in het tekstveld.");
            return;
        }
        
        btnParseEmail.disabled = true;
        parserLoader.style.display = "flex";
        parserResults.style.display = "none";
        
        try {
            const res = await fetch("/api/concerts/parse-email", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email_text: text })
            });
            
            const data = await res.json();
            if (res.ok) {
                parserResultsSummary.innerText = `Gemini heeft ${data.extracted_count} optredens gevonden. ${data.added_count} concerten zijn nieuw toegevoegd en gescoord.`;
                renderParserResults(data.added_concerts);
                parserResults.style.display = "block";
                newsletterText.value = ""; // leegmaken
            } else {
                alert(`Parser fout: ${data.detail || "Onbekend"}`);
            }
        } catch (err) {
            console.error(err);
            alert("Er is een fout opgetreden bij de parser API call.");
        } finally {
            btnParseEmail.disabled = false;
            parserLoader.style.display = "none";
        }
    });

    function renderParserResults(addedConcerts) {
        parserResultsGrid.innerHTML = "";
        
        if (addedConcerts.length === 0) {
            parserResultsGrid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 20px; color: var(--text-muted);">
                    Alle gevonden concerten stonden al in de database.
                </div>
            `;
            return;
        }
        
        addedConcerts.forEach(c => {
            const card = document.createElement("div");
            card.className = "card";
            
            let scoreClass = "low";
            if (c.calculated_score >= 8.0) scoreClass = "high";
            else if (c.calculated_score >= 5.0) scoreClass = "medium";
            
            const dateObj = new Date(c.date);
            const dateStr = dateObj.toLocaleDateString("nl-NL", { day: '2-digit', month: 'short', year: 'numeric' });
            const priceStr = c.price ? `€${c.price.toFixed(2)}` : 'Onbekend';
            
            card.innerHTML = `
                <div class="card-header">
                    <h4 style="font-weight: 700; color: #ffffff;">${c.artist}</h4>
                    <div class="score-badge ${scoreClass}">${c.calculated_score.toFixed(1)}</div>
                </div>
                <div class="card-body" style="font-size: 13px; gap: 5px;">
                    <div><i class="fa-solid fa-map-pin" style="color:var(--primary); margin-right:5px;"></i> ${c.venue ? c.venue.name : "Onbekend"}</div>
                    <div><i class="fa-solid fa-calendar" style="color:var(--primary); margin-right:5px;"></i> ${dateStr}</div>
                    <div><i class="fa-solid fa-coins" style="color:var(--primary); margin-right:5px;"></i> Prijs: ${priceStr}</div>
                </div>
            `;
            parserResultsGrid.appendChild(card);
        });
    }

    // --- Scrapers Functions (integrated in Venues) ---
    async function runVenueScraper(id) {
        try {
            const res = await fetch(`/api/venues/${id}/run_scraper`, { method: "POST" });
            if (res.ok) {
                alert("Scraper handmatig gestart! Vernieuw de pagina over een paar seconden om de resultaten en status te bekijken.");
                setTimeout(loadVenues, 3000);
            } else {
                const data = await res.json();
                alert("Fout bij starten scraper: " + data.detail);
            }
        } catch (err) {
            alert("Netwerkfout: " + err.message);
        }
    }

    async function toggleVenueScraperEnabled(id, enabled) {
        try {
            const venue = venues.find(v => v.id == id);
            if (venue) {
                const payload = {
                    name: venue.name,
                    category: venue.category,
                    latitude: venue.latitude,
                    longitude: venue.longitude,
                    url: venue.url,
                    aliases: venue.aliases,
                    
                    scraper_url: venue.scraper_url,
                    scraper_enabled: enabled,
                    scraper_code: venue.scraper_code
                };
                const res = await fetch(`/api/venues/${id}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (!res.ok) alert("Fout bij wijzigen status.");
            }
            loadVenues();
        } catch (err) {
            console.error(err);
        }
    }
    
    // Code Modal Handlers
    btnCloseCodeModal.addEventListener("click", () => {
        modalScraperCode.classList.remove("active");
    });
    btnCancelCode.addEventListener("click", () => {
        modalScraperCode.classList.remove("active");
    });
    
    scraperCodeForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = scraperCodeId.value;
        
        // Find the venue in local state to preserve other properties
        const venue = venues.find(v => v.id == id);
        if (!venue) {
            alert("Podium niet gevonden.");
            return;
        }
        
        const payload = {
            name: venue.name,
            category: venue.category,
            latitude: venue.latitude,
            longitude: venue.longitude,
            url: venue.url,
            aliases: venue.aliases,
            
            scraper_url: venue.scraper_url,
            scraper_enabled: scraperCodeEnabled.checked,
            scraper_code: scraperCodeTextarea.value
        };
        
        try {
            const res = await fetch(`/api/venues/${id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                modalScraperCode.classList.remove("active");
                loadVenues();
            } else {
                alert("Fout bij opslaan code.");
            }
        } catch (err) {
            console.error(err);
        }
    });
    
    // Manual healing handler
    btnHealScraperManual.addEventListener("click", async () => {
        const id = scraperCodeId.value;
        btnHealScraperManual.disabled = true;
        btnHealScraperManual.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Repareren...';
        
        try {
            const res = await fetch(`/api/venues/${id}/run_scraper?force_heal=true`, { method: "POST" });
            if (res.ok) {
                alert("Gemini reparatie gestart in de achtergrond! De code wordt automatisch herladen zodra deze gereed is.");
                setTimeout(async () => {
                    const venuesRes = await fetch("/api/venues");
                    const updatedVenues = await venuesRes.json();
                    venues = updatedVenues;
                    const v = venues.find(x => x.id == id);
                    if (v) {
                        scraperCodeTextarea.value = v.scraper_code || "";
                        scraperCodeEnabled.checked = v.scraper_enabled !== false;
                    }
                    btnHealScraperManual.disabled = false;
                    btnHealScraperManual.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Forceer Gemini Reparatie';
                    
                    if (activeTab === "venues") {
                        renderVenues();
                    } else if (activeTab === "scrapers") {
                        loadScrapers();
                    }
                }, 8000);
            } else {
                alert("Fout bij starten reparatie.");
                btnHealScraperManual.disabled = false;
                btnHealScraperManual.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Forceer Gemini Reparatie';
            }
        } catch (err) {
            alert(err.message);
            btnHealScraperManual.disabled = false;
            btnHealScraperManual.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Forceer Gemini Reparatie';
        }
    });

    // --- Scrapers Tab Functions ---
    async function loadScrapers() {
        try {
            scrapersTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center;"><span class="loader"></span><p>Scrapers laden...</p></td></tr>';
            const res = await fetch("/api/venues");
            venues = await res.json();
            scrapersTableBody.innerHTML = "";
            
            if (venues.length === 0) {
                scrapersTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center;" class="text-muted">Geen podia geconfigureerd. Voeg er een toe via het tabblad Podia of klik op Scraper Toevoegen!</td></tr>';
                return;
            }
            
            venues.forEach(s => {
                const tr = document.createElement("tr");
                
                let scraperUrlCol = '<span class="text-dark">-</span>';
                let statusBadge = '<span class="text-dark">-</span>';
                let lastRunTime = '<span class="text-dark">-</span>';
                let errorSnippet = '<span class="text-dark">-</span>';
                let enabledToggle = '';
                let scraperButtons = '';
                
                if (s.scraper_url) {
                    scraperUrlCol = `<div style="max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${s.scraper_url}"><a href="${s.scraper_url}" target="_blank" class="text-muted" style="text-decoration: underline;">${s.scraper_url}</a></div>`;
                    
                    // Status badge
                    statusBadge = '<span class="status-pill status-new">Nooit gedraaid</span>';
                    if (s.scraper_last_status === "success") {
                        statusBadge = '<span class="status-pill status-interested"><i class="fa-solid fa-check"></i> Succes</span>';
                    } else if (s.scraper_last_status === "failed") {
                        statusBadge = '<span class="status-pill status-ignored" style="cursor: pointer;" title="' + (s.scraper_error_log || '').replace(/"/g, '&quot;') + '"><i class="fa-solid fa-xmark"></i> Mislukt</span>';
                    }
                    
                    // Last run time
                    lastRunTime = s.scraper_last_run ? new Date(s.scraper_last_run).toLocaleString("nl-NL") : "Nooit";
                    
                    // Toggle switch for Enabled
                    enabledToggle = `
                        <label class="switch" style="position: relative; display: inline-block; width: 40px; height: 20px; margin-right: 10px; vertical-align: middle;">
                            <input type="checkbox" class="scraper-toggle-enabled" data-id="${s.id}" ${s.scraper_enabled !== false ? 'checked' : ''} style="opacity: 0; width: 0; height: 0;">
                            <span class="slider round" style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: ${s.scraper_enabled !== false ? '#6366f1' : '#ccc'}; transition: .4s; border-radius: 20px;"></span>
                        </label>
                    `;
                    
                    // Error snippet
                    errorSnippet = s.scraper_error_log ? `<div class="text-muted" style="max-width: 250px; font-family: monospace; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${s.scraper_error_log.replace(/"/g, '&quot;')}">${s.scraper_error_log}</div>` : "-";
                    
                    scraperButtons = `
                        <button class="btn btn-secondary btn-sm btn-run-scraper-tab" data-id="${s.id}" title="Nu draaien" style="margin-right: 5px; padding: 4px 8px; background: rgba(99, 102, 241, 0.15); color: #818cf8;">
                            <i class="fa-solid fa-play"></i> Run
                        </button>
                        <button class="btn btn-secondary btn-sm btn-view-code-tab" data-id="${s.id}" data-name="${s.name}" data-url="${s.scraper_url}" data-code="${(s.scraper_code || '').replace(/"/g, '&quot;')}" data-enabled="${s.scraper_enabled}" title="Bekijk code" style="margin-right: 5px; padding: 4px 8px;">
                            <i class="fa-solid fa-code"></i> Code
                        </button>
                    `;
                } else {
                    scraperUrlCol = '<span class="text-muted" style="font-style: italic;">Geen scraper link</span>';
                    scraperButtons = `
                        <button class="btn btn-secondary btn-sm btn-setup-scraper-tab" data-id="${s.id}" title="Scraper instellen" style="margin-right: 5px; padding: 4px 8px; background: rgba(16, 185, 129, 0.15); color: #34d399;">
                            <i class="fa-solid fa-plus"></i> Scraper instellen
                        </button>
                    `;
                }
                
                tr.innerHTML = `
                    <td style="font-weight: 600; color: #ffffff;">${s.name}</td>
                    <td>${scraperUrlCol}</td>
                    <td>${statusBadge}</td>
                    <td class="text-muted">${lastRunTime}</td>
                    <td>${errorSnippet}</td>
                    <td style="text-align: right; white-space: nowrap;">
                        ${enabledToggle}
                        ${scraperButtons}
                        <button class="btn btn-secondary btn-sm btn-edit-venue" data-id="${s.id}" style="margin-right: 5px;"><i class="fa-solid fa-pen"></i></button>
                        <button class="btn btn-danger btn-sm btn-delete-venue" data-id="${s.id}"><i class="fa-solid fa-trash"></i></button>
                    </td>
                `;
                
                if (s.scraper_url) {
                    tr.querySelector(".scraper-toggle-enabled").addEventListener("change", async (e) => {
                        const id = e.target.getAttribute("data-id");
                        const enabled = e.target.checked;
                        await toggleVenueScraperEnabled(id, enabled);
                        loadScrapers();
                    });
                    
                    tr.querySelector(".btn-run-scraper-tab").addEventListener("click", async (e) => {
                        const btnEl = e.currentTarget;
                        const id = btnEl.getAttribute("data-id");
                        btnEl.disabled = true;
                        btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running';
                        await runVenueScraper(id);
                        btnEl.disabled = false;
                        btnEl.innerHTML = '<i class="fa-solid fa-play"></i> Run';
                        loadScrapers();
                    });
                    
                    tr.querySelector(".btn-view-code-tab").addEventListener("click", () => {
                        scraperCodeId.value = s.id;
                        scraperCodeName.value = s.name;
                        scraperCodeUrl.value = s.scraper_url;
                        scraperCodeEnabled.checked = s.scraper_enabled !== false;
                        scraperCodeTitle.innerText = `Scraper Code: ${s.name}`;
                        scraperCodeTextarea.value = s.scraper_code || "";
                        modalScraperCode.classList.add("active");
                    });
                } else {
                    tr.querySelector(".btn-setup-scraper-tab").addEventListener("click", () => openScraperModal(s));
                }
                
                tr.querySelector(".btn-edit-venue").addEventListener("click", () => openScraperModal(s));
                tr.querySelector(".btn-delete-venue").addEventListener("click", () => deleteVenue(s.id));
                
                scrapersTableBody.appendChild(tr);
            });
        } catch (err) {
            console.error("Fout bij laden scrapers:", err);
            scrapersTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: red;">Fout bij inladen scrapers.</td></tr>';
        }
    }

    async function removeScraperLink(id) {
        try {
            const venue = venues.find(v => v.id == id);
            if (venue) {
                const payload = {
                    name: venue.name,
                    category: venue.category,
                    latitude: venue.latitude,
                    longitude: venue.longitude,
                    url: venue.url,
                    aliases: venue.aliases,
                    
                    scraper_url: null,
                    scraper_enabled: false,
                    scraper_code: null
                };
                const res = await fetch(`/api/venues/${id}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    loadScrapers();
                } else {
                    alert("Fout bij het verwijderen van de scraper link.");
                }
            }
        } catch (err) {
            console.error(err);
        }
    }

    // Scraper Modal Controls
    function openScraperModal(venue = null) {
        if (venue) {
            scraperModalTitle.innerText = "Custom Scraper Bewerken";
            scraperIdInput.value = venue.id;
            scraperFormName.value = venue.name;
            scraperFormUrl.value = venue.scraper_url || "";
            scraperFormEnabled.checked = venue.scraper_enabled !== false;
        } else {
            scraperModalTitle.innerText = "Custom Scraper Toevoegen";
            scraperIdInput.value = "";
            scraperForm.reset();
            scraperFormEnabled.checked = true;
        }
        modalScraper.classList.add("active");
    }

    btnAddScraper.addEventListener("click", () => openScraperModal());
    
    btnCloseScraperModal.addEventListener("click", () => {
        modalScraper.classList.remove("active");
    });
    
    btnCancelScraper.addEventListener("click", () => {
        modalScraper.classList.remove("active");
    });
    
    scraperForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = scraperIdInput.value;
        
        let payload = {};
        if (id) {
            // Edit existing scraper: find venue to preserve category, location, url, aliases, code
            const venue = venues.find(v => v.id == id);
            if (!venue) {
                alert("Podium niet gevonden.");
                return;
            }
            payload = {
                name: scraperFormName.value.trim(),
                category: venue.category,
                latitude: venue.latitude,
                longitude: venue.longitude,
                url: venue.url,
                aliases: venue.aliases,
                
                scraper_url: scraperFormUrl.value.trim() || null,
                scraper_enabled: scraperFormEnabled.checked,
                scraper_code: venue.scraper_code
            };
        } else {
            // Add new scraper
            payload = {
                name: scraperFormName.value.trim(),
                category: "medium",
                latitude: 52.0907, // Default Utrecht Centraal
                longitude: 5.1214,
                url: null,
                aliases: "",
                
                scraper_url: scraperFormUrl.value.trim() || null,
                scraper_enabled: scraperFormEnabled.checked,
                scraper_code: null
            };
        }
        
        btnSubmitScraper.disabled = true;
        btnSubmitScraper.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Opslaan...';
        
        const url = id ? `/api/venues/${id}` : "/api/venues";
        const method = id ? "PUT" : "POST";
        
        try {
            const res = await fetch(url, {
                method: method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                modalScraper.classList.remove("active");
                if (id) {
                    loadScrapers();
                } else {
                    alert("Scraper toegevoegd! Gemini genereert nu de scraping-code in de achtergrond.");
                    setTimeout(loadScrapers, 5000);
                }
            } else {
                const data = await res.json();
                alert("Fout bij opslaan scraper: " + data.detail);
            }
        } catch (err) {
            alert("Netwerkfout: " + err.message);
        } finally {
            btnSubmitScraper.disabled = false;
            btnSubmitScraper.innerHTML = "Opslaan";
        }
    });

    // --- Clipboard Copy ICS ---
    btnCopyIcs.addEventListener("click", () => {
        icsFeedUrlInput.select();
        icsFeedUrlInput.setSelectionRange(0, 99999); // Mobiel
        navigator.clipboard.writeText(icsFeedUrlInput.value);
        
        const origIcon = btnCopyIcs.innerHTML;
        btnCopyIcs.innerHTML = '<i class="fa-solid fa-check"></i> Gekopieerd!';
        btnCopyIcs.classList.add("btn-success");
        btnCopyIcs.classList.remove("btn-secondary");
        
        setTimeout(() => {
            btnCopyIcs.innerHTML = origIcon;
            btnCopyIcs.classList.remove("btn-success");
            btnCopyIcs.classList.add("btn-secondary");
        }, 2000);
    });

    // --- Init ---
    // Start met het inladen van de concerten (de active tab)
    loadConcerts();
});
