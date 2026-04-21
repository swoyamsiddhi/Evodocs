document.addEventListener('DOMContentLoaded', () => {
    const tagInputs = {
        proposed: { input: document.getElementById('proposed-input'), list: document.getElementById('proposed-tags'), tags: [] },
        current: { input: document.getElementById('current-input'), list: document.getElementById('current-tags'), tags: [] },
        allergies: { input: document.getElementById('allergies-input'), list: document.getElementById('allergies-tags'), tags: [] },
        conditions: { input: document.getElementById('conditions-input'), list: document.getElementById('conditions-tags'), tags: [] }
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
            li.innerHTML = `
                ${tag}
                <button type="button" onclick="window.removeTagRef('${category}', ${index})" aria-label="Remove ${tag}">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            `;
            state.list.appendChild(li);
        });
    }

    window.removeTagRef = removeTag;

    Object.keys(tagInputs).forEach(category => {
        const input = tagInputs[category].input;
        
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                const values = input.value.split(',');
                values.forEach(v => addTag(category, v));
                input.value = '';
            } else if (e.key === 'Backspace' && input.value === '' && tagInputs[category].tags.length > 0) {
                removeTag(category, tagInputs[category].tags.length - 1);
            }
        });

        input.addEventListener('blur', () => {
            if (input.value.trim()) {
                const values = input.value.split(',');
                values.forEach(v => addTag(category, v));
                input.value = '';
            }
        });
    });

    const form = document.getElementById('check-safety-form');
    const submitBtn = document.getElementById('submit-btn');
    const emptyState = document.getElementById('empty-state');
    const loadingState = document.getElementById('loading-state');
    const resultsState = document.getElementById('results-state');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (tagInputs.proposed.tags.length === 0) {
            if (tagInputs.proposed.input.value.trim()) {
                addTag('proposed', tagInputs.proposed.input.value);
                tagInputs.proposed.input.value = '';
            } else {
                alert('Please enter at least one proposed medicine.');
                tagInputs.proposed.input.focus();
                return;
            }
        }

        const ageVal = document.getElementById('age').value;
        const weightVal = document.getElementById('weight').value;

        const requestData = {
            proposed_medicines: tagInputs.proposed.tags,
            patient_history: {
                current_medications: tagInputs.current.tags,
                known_allergies: tagInputs.allergies.tags,
                conditions: tagInputs.conditions.tags,
                age: ageVal ? parseInt(ageVal, 10) : null,
                weight_kg: weightVal ? parseFloat(weightVal) : null
            }
        };

        submitBtn.disabled = true;
        emptyState.classList.add('hidden');
        resultsState.classList.add('hidden');
        loadingState.classList.remove('hidden');

        try {
            const response = await fetch('/check-safety', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail?.[0]?.msg || JSON.stringify(errorData.detail) || 'Failed to analyze safety');
            }

            const data = await response.json();
            renderResults(data);
        } catch (error) {
            console.error(error);
            alert('Error during analysis: ' + error.message);
            loadingState.classList.add('hidden');
            emptyState.classList.remove('hidden');
        } finally {
            submitBtn.disabled = false;
        }
    });

    function renderResults(data) {
        loadingState.classList.add('hidden');
        resultsState.classList.remove('hidden');

        document.getElementById('res-score').textContent = data.patient_risk_score !== undefined ? data.patient_risk_score : '--';
        document.getElementById('res-safe').textContent = data.safe_to_prescribe ? "YES" : "NO";
        document.getElementById('res-risk').textContent = String(data.overall_risk_level).toUpperCase();

        const cardSafe = document.getElementById('card-safety');
        cardSafe.className = 'summary-card glass-panel ' + (data.safe_to_prescribe ? 'safe' : 'danger');

        const cardRisk = document.getElementById('card-risk');
        let riskClass = 'safe';
        if (data.overall_risk_level === 'high') riskClass = 'danger';
        else if (data.overall_risk_level === 'medium') riskClass = 'warning';
        cardRisk.className = 'summary-card glass-panel ' + riskClass;

        document.getElementById('res-source').querySelector('span').textContent = String(data.source).toUpperCase();
        document.getElementById('res-cache').querySelector('span').textContent = data.cache_hit ? 'HIT' : 'MISS';
        document.getElementById('res-time').querySelector('span').textContent = data.processing_time_ms;

        renderList('allergies', data.allergy_alerts, (alert) => `
            <div class="alert-card sev-${alert.severity}">
                <div style="flex:1">
                    <div class="alert-header">
                        <div class="alert-title">${alert.medicine}</div>
                        <div class="alert-badge sev-${alert.severity}">${alert.severity}</div>
                    </div>
                    <div class="alert-body">
                        <p>${alert.reason}</p>
                    </div>
                </div>
            </div>
        `);

        renderList('contraindications', data.contraindication_alerts, (alert) => `
            <div class="alert-card sev-${alert.severity}">
                <div style="flex:1">
                    <div class="alert-header">
                        <div class="alert-title">${alert.medicine} ➔ ${alert.condition}</div>
                        <div class="alert-badge sev-${alert.severity}">${alert.severity}</div>
                    </div>
                    <div class="alert-body">
                        <p>${alert.reason}</p>
                    </div>
                </div>
            </div>
        `);

        renderList('interactions', data.interactions, (alert) => `
            <div class="alert-card sev-${alert.severity}">
                <div style="flex:1">
                    <div class="alert-header">
                        <div class="alert-title">${alert.drug_a} + ${alert.drug_b}</div>
                        <div class="alert-badge sev-${alert.severity}">${alert.severity}</div>
                    </div>
                    <div class="alert-body">
                        <p>${alert.mechanism}</p>
                        ${alert.clinical_recommendation ? `
                            <div class="alert-recommendation">
                                <strong><i class="fa-solid fa-user-doctor"></i> Recommendation:</strong> ${alert.clinical_recommendation}
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `);
    }

    function renderList(sectionId, items, htmlMapFn) {
        const section = document.getElementById(`section-${sectionId}`);
        const container = document.getElementById(`list-${sectionId}`);
        container.innerHTML = '';

        if (!items || items.length === 0) {
            section.classList.remove('active');
        } else {
            section.classList.add('active');
            items.forEach(item => {
                container.innerHTML += htmlMapFn(item);
            });
        }
    }
});
