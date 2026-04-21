document.addEventListener('DOMContentLoaded', () => {

    /* =============================================
       Tag Input System
       ============================================= */
    const tagInputs = {
        proposed:    { input: document.getElementById('proposed-input'),    list: document.getElementById('proposed-tags'),    tags: [] },
        current:     { input: document.getElementById('current-input'),     list: document.getElementById('current-tags'),     tags: [] },
        allergies:   { input: document.getElementById('allergies-input'),   list: document.getElementById('allergies-tags'),   tags: [] },
        conditions:  { input: document.getElementById('conditions-input'),  list: document.getElementById('conditions-tags'),  tags: [] },
    };

    function addTag(category, value) {
        value = value.trim();
        if (!value) return;
        const state = tagInputs[category];
        if (state.tags.some(t => t.toLowerCase() === value.toLowerCase())) return;
        state.tags.push(value);
        renderTags(category);
    }

    function removeTag(category, index) {
        tagInputs[category].tags.splice(index, 1);
        renderTags(category);
    }

    function renderTags(category) {
        const state = tagInputs[category];
        state.list.innerHTML = '';
        state.tags.forEach((tag, index) => {
            const li = document.createElement('li');
            li.className = 'tag';
            li.innerHTML = `${tag}<button type="button" onclick="window._removeTag('${category}',${index})" aria-label="Remove ${tag}"><i class="fa-solid fa-xmark"></i></button>`;
            state.list.appendChild(li);
        });
        // Click on container focuses input
        const box = state.input.closest('.tag-box');
        if (box) box.onclick = () => state.input.focus();
    }

    window._removeTag = removeTag;

    Object.keys(tagInputs).forEach(category => {
        const input = tagInputs[category].input;
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                input.value.split(',').forEach(v => addTag(category, v));
                input.value = '';
            } else if (e.key === 'Backspace' && input.value === '' && tagInputs[category].tags.length > 0) {
                removeTag(category, tagInputs[category].tags.length - 1);
            }
        });
        input.addEventListener('blur', () => {
            if (input.value.trim()) {
                input.value.split(',').forEach(v => addTag(category, v));
                input.value = '';
            }
        });
    });

    /* =============================================
       Tab System
       ============================================= */
    document.getElementById('alerts-tabs').addEventListener('click', (e) => {
        const btn = e.target.closest('.tab-btn');
        if (!btn) return;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
        btn.classList.add('active');
        const target = document.getElementById(btn.dataset.target);
        if (target) target.classList.remove('hidden');
    });

    /* =============================================
       Form Submission
       ============================================= */
    const form        = document.getElementById('check-safety-form');
    const submitBtn   = document.getElementById('submit-btn');
    const emptyState  = document.getElementById('empty-state');
    const loadingState = document.getElementById('loading-state');
    const resultsState = document.getElementById('results-state');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Auto-commit any pending text in proposed input
        if (tagInputs.proposed.tags.length === 0) {
            const raw = tagInputs.proposed.input.value.trim();
            if (raw) {
                raw.split(',').forEach(v => addTag('proposed', v));
                tagInputs.proposed.input.value = '';
            } else {
                tagInputs.proposed.input.focus();
                tagInputs.proposed.input.style.borderBottom = '2px solid #FF5555';
                setTimeout(() => { tagInputs.proposed.input.style.borderBottom = ''; }, 1500);
                return;
            }
        }

        const ageVal    = document.getElementById('age').value;
        const weightVal = document.getElementById('weight').value;

        const payload = {
            proposed_medicines: tagInputs.proposed.tags,
            patient_history: {
                current_medications: tagInputs.current.tags,
                known_allergies:     tagInputs.allergies.tags,
                conditions:          tagInputs.conditions.tags,
                age:       ageVal    ? parseInt(ageVal, 10)   : null,
                weight_kg: weightVal ? parseFloat(weightVal)  : null,
            }
        };

        submitBtn.disabled = true;
        emptyState.classList.add('hidden');
        resultsState.classList.add('hidden');
        loadingState.classList.remove('hidden');

        try {
            const res = await fetch('/check-safety', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail?.[0]?.msg || JSON.stringify(err.detail) || `HTTP ${res.status}`);
            }

            const data = await res.json();
            renderResults(data);
        } catch (err) {
            console.error(err);
            loadingState.classList.add('hidden');
            emptyState.classList.remove('hidden');
            showToast(`Analysis failed: ${err.message}`, 'error');
        } finally {
            submitBtn.disabled = false;
        }
    });

    /* =============================================
       Render Results
       ============================================= */
    function renderResults(data) {
        loadingState.classList.add('hidden');
        resultsState.classList.remove('hidden');

        // Summary cards
        const safe     = data.safe_to_prescribe;
        const risk     = (data.overall_risk_level || '').toLowerCase();
        const score    = data.patient_risk_score ?? 0;

        document.getElementById('res-safe').textContent = safe ? 'YES' : 'NO';
        document.getElementById('res-risk').textContent = risk.toUpperCase();
        document.getElementById('res-score').textContent = score;

        const cardSafe  = document.getElementById('card-safety');
        const cardRisk  = document.getElementById('card-risk');
        const cardScore = document.getElementById('card-score');

        cardSafe.className  = 'sum-card glass ' + (safe ? 'safe' : 'danger');
        cardScore.className = 'sum-card glass ' + riskClass(risk);
        if (risk === 'high')   cardRisk.className = 'sum-card glass danger';
        else if (risk === 'medium') cardRisk.className = 'sum-card glass medium';
        else cardRisk.className = 'sum-card glass safe';

        // Risk breakdown logic removed to match new UI

        // Meta chips
        const srcEl  = document.getElementById('chip-source');
        const source = (data.source || '').toLowerCase();
        document.getElementById('res-source-val').textContent = source.toUpperCase();
        srcEl.className = `meta-chip src-${source}`;
        document.getElementById('res-cache-val').textContent = data.cache_hit ? 'HIT' : 'MISS';
        document.getElementById('res-time-val').textContent  = data.processing_time_ms ?? '--';

        // Doctor review banner
        const banner = document.getElementById('review-banner');
        banner.classList.toggle('hidden', !data.requires_doctor_review);

        // Alert lists
        renderInteractions(data.interactions || []);
        renderAllergies(data.allergy_alerts || []);
        renderContraindications(data.contraindication_alerts || []);

        // Auto-switch to first non-empty tab
        const counts = {
            interactions:     (data.interactions || []).length,
            allergies:        (data.allergy_alerts || []).length,
            contraindications:(data.contraindication_alerts || []).length,
        };
        // Switch tab to highest priority alert category
        const priority = ['allergies','contraindications','interactions'];
        const firstNonEmpty = priority.find(k => counts[k] > 0);
        if (firstNonEmpty) switchTab(`tab-${firstNonEmpty}`);
        else switchTab('tab-interactions');
    }

    function switchTab(targetId) {
        document.querySelectorAll('.tab-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.target === targetId);
        });
        document.querySelectorAll('.tab-panel').forEach(p => {
            p.classList.toggle('hidden', p.id !== targetId);
        });
    }

    function riskClass(risk) {
        if (risk === 'high') return 'danger';
        if (risk === 'medium') return 'medium';
        return 'safe';
    }

    /* =============================================
       Alert Card Builders
       ============================================= */

    function makeExpandCard(htmlMain, htmlDetail) {
        const card = document.createElement('div');
        card.className = 'alert-card';
        card.innerHTML = htmlMain;

        const expandBtn = document.createElement('button');
        expandBtn.className = 'expand-btn';
        expandBtn.type = 'button';
        expandBtn.innerHTML = `<span><i class="fa-solid fa-microscope"></i> View Details</span><i class="fa-solid fa-chevron-down expand-icon"></i>`;

        const detail = document.createElement('div');
        detail.className = 'alert-detail';
        detail.innerHTML = htmlDetail;

        expandBtn.addEventListener('click', () => {
            const isOpen = detail.classList.contains('open');
            detail.classList.toggle('open', !isOpen);
            expandBtn.classList.toggle('open', !isOpen);
            expandBtn.querySelector('span').innerHTML = isOpen
                ? '<i class="fa-solid fa-microscope"></i> View Details'
                : '<i class="fa-solid fa-microscope"></i> Hide Details';
        });

        card.appendChild(expandBtn);
        card.appendChild(detail);
        return card;
    }

    function sevIcon(sev) {
        const map = { critical: 'fa-radiation', high: 'fa-circle-exclamation', medium: 'fa-triangle-exclamation', low: 'fa-circle-info' };
        return map[sev] || 'fa-circle-info';
    }

    function renderInteractions(items) {
        const list = document.getElementById('list-interactions');
        document.getElementById('cnt-interactions').textContent = items.length;
        list.innerHTML = '';

        if (!items.length) {
            list.innerHTML = `<div class="no-issues"><i class="fa-solid fa-circle-check"></i> No drug interactions detected.</div>`;
            return;
        }

        items.forEach((item, i) => {
            const sev = (item.severity || 'low').toLowerCase();
            const main = `
                <div class="alert-stripe"></div>
                <div class="alert-main">
                    <div class="alert-top">
                        <div class="alert-drugs">
                            <span class="drug-pill">${capitalize(item.drug_a)}</span>
                            <span class="drug-sep">+</span>
                            <span class="drug-pill">${capitalize(item.drug_b)}</span>
                        </div>
                        <span class="sev-badge"><i class="fa-solid ${sevIcon(sev)}"></i> ${sev}</span>
                    </div>
                    ${item.mechanism ? `<div class="detail-text" style="font-size:.875rem;color:var(--text-2);line-height:1.6;">${item.mechanism}</div>` : ''}
                </div>
            `;

            const detail = `
                ${item.mechanism ? `
                    <div class="detail-block">
                        <div class="detail-label"><i class="fa-solid fa-flask"></i> Pharmacological Mechanism</div>
                        <div class="detail-text">${item.mechanism}</div>
                    </div>
                ` : ''}
                ${item.clinical_recommendation ? `
                    <div class="recommendation-block">
                        <div class="detail-label"><i class="fa-solid fa-user-doctor"></i> Clinical Recommendation</div>
                        <div class="detail-text">${item.clinical_recommendation}</div>
                    </div>
                ` : ''}
                ${item.source_confidence ? `
                    <div class="detail-block">
                        <div class="detail-label"><i class="fa-solid fa-star"></i> Source Confidence</div>
                        <div class="detail-text">${capitalize(item.source_confidence)}</div>
                    </div>
                ` : ''}
            `;

            const card = makeExpandCard(main, detail);
            card.classList.add(`sev-${sev}`);
            card.style.animationDelay = `${i * 60}ms`;
            list.appendChild(card);
        });
    }

    function renderAllergies(items) {
        const list = document.getElementById('list-allergies');
        document.getElementById('cnt-allergies').textContent = items.length;
        list.innerHTML = '';

        if (!items.length) {
            list.innerHTML = `<div class="no-issues"><i class="fa-solid fa-circle-check"></i> No allergy alerts detected.</div>`;
            return;
        }

        items.forEach((item, i) => {
            const sev = (item.severity || 'high').toLowerCase();
            const main = `
                <div class="alert-stripe"></div>
                <div class="alert-main">
                    <div class="alert-top">
                        <div class="alert-drugs">
                            <span class="drug-pill">${capitalize(item.medicine)}</span>
                        </div>
                        <span class="sev-badge"><i class="fa-solid ${sevIcon(sev)}"></i> ${sev}</span>
                    </div>
                    <div class="detail-text" style="font-size:.875rem;color:var(--text-2);line-height:1.6;">${item.reason}</div>
                </div>
            `;

            const detail = `
                <div class="detail-block">
                    <div class="detail-label"><i class="fa-solid fa-triangle-exclamation"></i> Allergy Reason</div>
                    <div class="detail-text">${item.reason}</div>
                </div>
                <div class="recommendation-block">
                    <div class="detail-label"><i class="fa-solid fa-user-doctor"></i> Clinical Recommendation</div>
                    <div class="detail-text">Avoid prescribing <strong>${capitalize(item.medicine)}</strong>. Review patient allergy history and select a pharmacologically unrelated alternative. Inform the patient and document in their medical record.</div>
                </div>
            `;

            const card = makeExpandCard(main, detail);
            card.classList.add(`sev-${sev}`);
            card.style.animationDelay = `${i * 60}ms`;
            list.appendChild(card);
        });
    }

    function renderContraindications(items) {
        const list = document.getElementById('list-contraindications');
        document.getElementById('cnt-contraindications').textContent = items.length;
        list.innerHTML = '';

        if (!items.length) {
            list.innerHTML = `<div class="no-issues"><i class="fa-solid fa-circle-check"></i> No contraindications detected.</div>`;
            return;
        }

        items.forEach((item, i) => {
            const sev = (item.severity || 'high').toLowerCase();
            const main = `
                <div class="alert-stripe"></div>
                <div class="alert-main">
                    <div class="alert-top">
                        <div class="alert-drugs">
                            <span class="drug-pill">${capitalize(item.medicine)}</span>
                            <span class="drug-sep">→</span>
                            <span class="drug-pill condition-pill">${capitalize(item.condition)}</span>
                        </div>
                        <span class="sev-badge"><i class="fa-solid ${sevIcon(sev)}"></i> ${sev}</span>
                    </div>
                    <div class="detail-text" style="font-size:.875rem;color:var(--text-2);line-height:1.6;">${item.reason}</div>
                </div>
            `;

            const detail = `
                <div class="detail-block">
                    <div class="detail-label"><i class="fa-solid fa-stethoscope"></i> Condition</div>
                    <div class="detail-text">${capitalize(item.condition)}</div>
                </div>
                <div class="detail-block">
                    <div class="detail-label"><i class="fa-solid fa-flask"></i> Contraindication Reason</div>
                    <div class="detail-text">${item.reason}</div>
                </div>
                <div class="recommendation-block">
                    <div class="detail-label"><i class="fa-solid fa-user-doctor"></i> Clinical Recommendation</div>
                    <div class="detail-text">Avoid prescribing <strong>${capitalize(item.medicine)}</strong> in a patient with <strong>${capitalize(item.condition)}</strong>. Consult a specialist and consider a safer therapeutic alternative.</div>
                </div>
            `;

            const card = makeExpandCard(main, detail);
            card.classList.add(`sev-${sev}`);
            card.style.animationDelay = `${i * 60}ms`;
            list.appendChild(card);
        });
    }

    /* =============================================
       Utilities
       ============================================= */
    function capitalize(str) {
        if (!str) return '';
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    function showToast(message, type = 'info') {
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.style.cssText = `
            position:fixed; bottom:1.5rem; right:1.5rem; z-index:9999;
            background: ${type === 'error' ? 'rgba(255,85,85,.15)' : 'rgba(79,127,255,.15)'};
            border: 1px solid ${type === 'error' ? 'rgba(255,85,85,.4)' : 'rgba(79,127,255,.4)'};
            color: var(--text-1); padding: .875rem 1.25rem;
            border-radius: 12px; font-size: .875rem; font-weight: 600;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px rgba(0,0,0,.4);
            max-width: 380px;
            animation: slideUp .25s ease;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity .3s'; setTimeout(() => toast.remove(), 300); }, 4000);
    }
});
