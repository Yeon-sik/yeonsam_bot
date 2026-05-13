async function loadGamePage() {
    const jsonPath = document.body.dataset.gameJson;
    const fallbackNode = document.getElementById("game-data-fallback");
    const tabList = document.getElementById("game-tab-list");
    const subtabList = document.getElementById("game-subtab-list");
    const panel = document.getElementById("game-panel");
    const panelLabel = document.getElementById("game-panel-label");
    const title = document.querySelector(".game-page-title");
    const genre = document.getElementById("game-genre");
    const summary = document.getElementById("game-summary");
    const detailList = document.getElementById("game-detail-list");
    const heroImage = document.getElementById("game-hero-image");

    if (!jsonPath || !tabList || !subtabList || !panel || !panelLabel || !title || !genre || !summary || !detailList || !heroImage) {
        return;
    }

    try {
        const data = await loadGameData(jsonPath, fallbackNode);
        const tabs = [
            { id: "guides", label: "공략 탭" },
            { id: "install", label: "설치 탭" }
        ];
        const state = {
            tabId: "guides",
            subtabId: getPreferredCategoryId(data.guides)
        };

        panelLabel.textContent = data.slug.toUpperCase();
        title.textContent = data.name;
        genre.textContent = data.description.genre;
        summary.textContent = data.description.summary;
        detailList.innerHTML = data.description.details
            .map((item) => `<li>${escapeHtml(item)}</li>`)
            .join("");
        heroImage.src = data.profileImage;
        heroImage.alt = `${data.name} profile`;

        renderTabButtons(tabs, state, data, tabList, subtabList, panel);
        renderContent(state, data, subtabList, panel);
    } catch (error) {
        panel.innerHTML = '<p class="game-error">게임 데이터를 불러오지 못했습니다.</p>';
    }
}

async function loadGameData(jsonPath, fallbackNode) {
    if (window.location.protocol !== "file:") {
        try {
            const response = await fetch(jsonPath);
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            // Fall back to inline JSON below when fetch is unavailable.
        }
    }

    if (fallbackNode?.textContent) {
        return JSON.parse(fallbackNode.textContent);
    }

    throw new Error("Could not load game JSON");
}

function renderTabButtons(tabs, state, data, tabList, subtabList, panel) {
    tabList.innerHTML = "";

    tabs.forEach((tab) => {
        const button = createSectionButton(tab.label, "tab-button", tab.id === state.tabId);
        button.addEventListener("click", () => {
            state.tabId = tab.id;
            state.subtabId = null;
            syncActiveButton(tabList, button);
            renderContent(state, data, subtabList, panel);
        });
        tabList.appendChild(button);
    });
}

function renderContent(state, data, subtabList, panel) {
    const categories = data[state.tabId] ?? [];
    const activeCategory = resolveActiveCategory(categories, state);

    renderSubtabButtons(categories, activeCategory, state, subtabList, panel);
    renderCategory(activeCategory, panel, state.tabId);
}

function renderSubtabButtons(categories, activeCategory, state, subtabList, panel) {
    subtabList.innerHTML = "";
    subtabList.hidden = categories.length === 0;

    categories.forEach((category) => {
        const button = createSectionButton(category.label, "subtab-button", category.id === activeCategory?.id);
        button.addEventListener("click", () => {
            state.subtabId = category.id;
            syncActiveButton(subtabList, button);
            renderCategory(category, panel, state.tabId);
        });
        subtabList.appendChild(button);
    });
}

function renderCategory(category, panel, tabId) {
    if (!category) {
        panel.innerHTML = '<p class="game-error">표시할 세부 항목이 없습니다.</p>';
        return;
    }

    if (category.id === "monsters" && Array.isArray(category.monsters) && category.monsters.length > 0) {
        renderMonsterCategory(category, panel);
        return;
    }

    const cards = category.groups
        .map((group) => (shouldRenderGuideMediaCards(category, tabId)
            ? renderGuideGroupCard(group, category)
            : renderDefaultGroupCard(group)))
        .join("");

    panel.innerHTML = `
        <div class="panel-heading">
            <p class="panel-label">DETAIL</p>
            <h2 class="game-section-title">${escapeHtml(category.title)}</h2>
        </div>
        <div class="detail-grid">${cards}</div>
    `;
}

function renderDefaultGroupCard(group) {
    const items = group.items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");

    return `
        <article class="detail-card pixel-box">
            <h3>${escapeHtml(group.title)}</h3>
            <ul>${items}</ul>
        </article>
    `;
}

function renderGuideGroupCard(group, category) {
    const items = group.items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const media = renderCardMedia(group.image, group.imageAlt ?? `${group.title} image`);

    return `
        <article class="detail-card detail-card-media pixel-box">
            <div class="monster-card-media">
                ${media}
            </div>
            <div class="detail-card-copy">
                <div class="monster-card-header">
                    <div>
                        <p class="monster-card-kicker">${escapeHtml(category.label)} GUIDE</p>
                        <h3>${escapeHtml(group.title)}</h3>
                    </div>
                    <div class="monster-card-tags">
                        <span class="monster-tag">${escapeHtml(category.label)}</span>
                    </div>
                </div>
                <ul>${items}</ul>
            </div>
        </article>
    `;
}

function shouldRenderGuideMediaCards(category, tabId) {
    if (tabId !== "guides") {
        return false;
    }

    return ["maps", "items", "mods"].includes(category.id);
}

function renderMonsterCategory(category, panel) {
    const insideMonsters = category.monsters.filter((monster) => monster.section === "inside");
    const outsideMonsters = category.monsters.filter((monster) => monster.section === "outside");
    const dummyMonsters = category.monsters.filter((monster) => monster.section === "dummy");
    const insideIndexLinks = renderIndexLinks(insideMonsters);
    const outsideIndexLinks = renderIndexLinks(outsideMonsters);
    const dummyIndexLinks = renderIndexLinks(dummyMonsters);
    const insideCards = insideMonsters.map((monster) => renderMonsterCard(monster)).join("");
    const outsideCards = outsideMonsters.map((monster) => renderMonsterCard(monster)).join("");
    const dummyCards = dummyMonsters.map((monster) => renderMonsterCard(monster)).join("");

    panel.innerHTML = `
        <div class="panel-heading">
            <p class="panel-label">DETAIL</p>
            <h2 class="game-section-title">${escapeHtml(category.title)}</h2>
            <p class="section-lead">
                내부와 외부 위협을 분리해 빠르게 판단할 수 있도록 정리한 실전형 몬스터 브리핑입니다.
                탐사 도중 필요한 핵심 정보만 바로 찾을 수 있게 구성했습니다.
            </p>
            <div class="monster-summary-strip">
                <article class="summary-chip pixel-box">
                    <span class="summary-chip-label">전체 몬스터</span>
                    <strong>${category.monsters.length}</strong>
                </article>
                <article class="summary-chip pixel-box">
                    <span class="summary-chip-label">내부 위협</span>
                    <strong>${insideMonsters.length}</strong>
                </article>
                <article class="summary-chip pixel-box">
                    <span class="summary-chip-label">외부 위협</span>
                    <strong>${outsideMonsters.length}</strong>
                </article>
                <article class="summary-chip pixel-box">
                    <span class="summary-chip-label">더미 데이터</span>
                    <strong>${dummyMonsters.length}</strong>
                </article>
            </div>
        </div>
        <div class="monster-index pixel-box">
            <div class="monster-index-header">
                <div>
                    <p class="panel-label">MONSTER INDEX</p>
                    <p class="monster-index-copy">이름을 누르면 해당 몬스터 카드로 바로 이동합니다.</p>
                </div>
            </div>
            <div class="monster-index-group">
                <p class="panel-label">내부 탭</p>
                <div class="monster-index-list">${insideIndexLinks}</div>
            </div>
            <div class="monster-index-group">
                <p class="panel-label">외부 탭</p>
                <div class="monster-index-list">${outsideIndexLinks}</div>
            </div>
            <div class="monster-index-group">
                <p class="panel-label">더미 탭</p>
                <div class="monster-index-list">${dummyIndexLinks}</div>
            </div>
        </div>
        <section class="monster-section">
            <div class="monster-section-heading">
                <div>
                    <p class="panel-label">INSIDE</p>
                    <h3 class="game-section-title">내부 몬스터</h3>
                </div>
                <p class="monster-section-copy">
                    시설 내부에서 조우하는 위협입니다. 시야 차단, 통로 구조, 팀 간 거리 관리가 핵심입니다.
                </p>
            </div>
            <div class="monster-card-list">${insideCards}</div>
        </section>
        <section class="monster-section">
            <div class="monster-section-heading">
                <div>
                    <p class="panel-label">OUTSIDE</p>
                    <h3 class="game-section-title">외부 몬스터</h3>
                </div>
                <p class="monster-section-copy">
                    기지 외곽과 이동 동선에서 만나는 위협입니다. 소음, 개활지 노출, 귀환 경로 확보가 중요합니다.
                </p>
            </div>
            <div class="monster-card-list">${outsideCards}</div>
        </section>
        <section class="monster-section">
            <div class="monster-section-heading">
                <div>
                    <p class="panel-label">DUMMY</p>
                    <h3 class="game-section-title">더미 몬스터</h3>
                </div>
                <p class="monster-section-copy">
                    정식 분류와 별도로 남겨둔 더미 데이터입니다. 현재 기준으로는 Lasso Man만 이 섹션에 표시됩니다.
                </p>
            </div>
            <div class="monster-card-list">${dummyCards}</div>
        </section>
    `;
}

function renderIndexLinks(monsters) {
    return monsters
        .map((monster) => `
            <a class="tab-button monster-index-link" href="#monster-${escapeHtml(monster.id)}">
                <span class="monster-index-name">${escapeHtml(monster.name)}</span>
                <span class="monster-index-subname">${escapeHtml(monster.nameKr ?? "0")}</span>
                ${isDummyMonster(monster) ? '<span class="monster-index-flag">DUMMY</span>' : ""}
            </a>
        `)
        .join("");
}

function renderMonsterCard(monster) {
    const threatTag = buildThreatTag(monster.health);
    const sectionTag = getMonsterSectionLabel(monster.section);
    const dummyTag = isDummyMonster(monster) ? '<span class="monster-tag monster-tag-dummy">DUMMY</span>' : "";
    const media = renderCardMedia(monster.image, monster.name);

    return `
        <article class="monster-card pixel-box" id="monster-${escapeHtml(monster.id)}">
            <div class="monster-card-media">
                ${media}
            </div>
            <div class="monster-card-copy">
                <div class="monster-card-header">
                    <div>
                        <p class="monster-card-kicker">${escapeHtml(sectionTag)} 몬스터</p>
                        <h3>${escapeHtml(monster.name)}</h3>
                        <p class="monster-card-subtitle">${escapeHtml(monster.nameKr ?? "0")}</p>
                    </div>
                    <div class="monster-card-tags">
                        <span class="monster-tag">${escapeHtml(sectionTag)}</span>
                        <span class="monster-tag monster-tag-accent">${escapeHtml(threatTag)}</span>
                        ${dummyTag}
                    </div>
                </div>
                <dl class="monster-meta-list">
                    <div>
                        <dt>체력</dt>
                        <dd>${escapeHtml(monster.health)}</dd>
                    </div>
                    <div class="monster-meta-wide">
                        <dt>설명</dt>
                        <dd>${escapeHtml(monster.description)}</dd>
                    </div>
                    <div class="monster-meta-wide">
                        <dt>공략</dt>
                        <dd>${escapeHtml(monster.strategy)}</dd>
                    </div>
                </dl>
            </div>
        </article>
    `;
}

function renderCardMedia(image, alt) {
    if (image) {
        return `<img src="${escapeHtml(image)}" alt="${escapeHtml(alt)}">`;
    }

    return `<div class="monster-image-placeholder" aria-label="${escapeHtml(alt)} image unavailable">NO IMAGE</div>`;
}

function buildThreatTag(health) {
    const value = String(health);

    if (value.includes("매우")) {
        return "최상위 위협";
    }

    if (value.includes("즉사") || value.includes("무적")) {
        return "고위험";
    }

    if (value.includes("높음")) {
        return "위험";
    }

    if (value.includes("중간")) {
        return "주의";
    }

    if (value.includes("낮음")) {
        return "저위험";
    }

    return "특수";
}

function isDummyMonster(monster) {
    return monster.section === "dummy";
}

function getMonsterSectionLabel(section) {
    if (section === "inside") {
        return "내부";
    }

    if (section === "outside") {
        return "외부";
    }

    return "더미";
}

function getPreferredCategoryId(categories) {
    if (!Array.isArray(categories) || categories.length === 0) {
        return null;
    }

    const monsterCategory = categories.find((category) => category.id === "monsters");
    return monsterCategory?.id ?? categories[0].id;
}

function resolveActiveCategory(categories, state) {
    if (categories.length === 0) {
        state.subtabId = null;
        return null;
    }

    const matched = categories.find((category) => category.id === state.subtabId);
    if (matched) {
        return matched;
    }

    state.subtabId = categories[0].id;
    return categories[0];
}

function createSectionButton(label, className, isActive) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    if (isActive) {
        button.classList.add("is-active");
    }
    return button;
}

function syncActiveButton(container, activeButton) {
    container.querySelectorAll("button").forEach((node) => node.classList.remove("is-active"));
    activeButton.classList.add("is-active");
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

loadGamePage();
