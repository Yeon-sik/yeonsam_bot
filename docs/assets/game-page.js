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
        const hashRoutes = buildHashRoutes(data);

        panelLabel.textContent = String(data.slug ?? "").toUpperCase();
        title.textContent = data.name ?? "";
        genre.textContent = data.description?.genre ?? "";
        summary.textContent = data.description?.summary ?? "";
        detailList.innerHTML = (data.description?.details ?? [])
            .map((item) => `<li>${escapeHtml(item)}</li>`)
            .join("");
        heroImage.src = data.profileImage ?? "";
        heroImage.alt = `${data.name ?? "game"} profile`;

        applyHashState(window.location.hash, state, hashRoutes);
        renderPage(tabs, state, data, tabList, subtabList, panel);
        scrollToHashTarget(window.location.hash);
        bindHashNavigation(tabs, state, data, hashRoutes, tabList, subtabList, panel);
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

function renderPage(tabs, state, data, tabList, subtabList, panel) {
    renderTabButtons(tabs, state, data, tabList, subtabList, panel);
    renderContent(state, data, subtabList, panel);
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

    if (Array.isArray(category.monsters) && category.monsters.length > 0) {
        renderMonsterCategory(category, panel);
        return;
    }

    if (category.groups?.some((group) => Array.isArray(group.entries) && group.entries.length > 0)) {
        renderRecordCategory(category, panel);
        return;
    }

    const cards = (category.groups ?? [])
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
    const items = (group.items ?? []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");

    return `
        <article class="detail-card pixel-box">
            <h3>${escapeHtml(group.title)}</h3>
            <ul>${items}</ul>
        </article>
    `;
}

function renderGuideGroupCard(group, category) {
    const items = (group.items ?? []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");

    return `
        <article class="detail-card detail-card-media pixel-box">
            <div class="monster-card-media">
                ${renderCardMedia(group.image, group.imageAlt ?? group.title)}
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
    return tabId === "guides" && ["maps", "items", "mods"].includes(category.id);
}

function renderRecordCategory(category, panel) {
    const sections = (category.groups ?? [])
        .map((group) => {
            const cards = (group.entries ?? [])
                .map((entry) => renderRecordCard(category, group, entry))
                .join("");

            return `
                <section class="record-section">
                    <div class="record-section-heading">
                        <div>
                            <p class="panel-label">${escapeHtml((group.label ?? group.title ?? "").toUpperCase())}</p>
                            <h3 class="game-section-title">${escapeHtml(group.title)}</h3>
                        </div>
                        ${group.description ? `<p class="record-section-copy">${escapeHtml(group.description)}</p>` : ""}
                    </div>
                    <div class="record-card-list">${cards}</div>
                </section>
            `;
        })
        .join("");

    panel.innerHTML = `
        <div class="panel-heading">
            <p class="panel-label">DETAIL</p>
            <h2 class="game-section-title">${escapeHtml(category.title)}</h2>
        </div>
        ${sections}
    `;
}

function renderMonsterCategory(category, panel) {
    const insideMonsters = category.monsters.filter((monster) => monster.section === "inside");
    const outsideMonsters = category.monsters.filter((monster) => monster.section === "outside");
    const dummyMonsters = category.monsters.filter((monster) => monster.section === "dummy");

    panel.innerHTML = `
        <div class="panel-heading">
            <p class="panel-label">DETAIL</p>
            <h2 class="game-section-title">${escapeHtml(category.title)}</h2>
            <p class="section-lead">
                내부, 외부, 더미 몬스터를 분리해 빠르게 판단할 수 있도록 정리한 실전형 몬스터 브리핑입니다.
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
                <p class="panel-label">내부</p>
                <div class="monster-index-list">${renderIndexLinks(insideMonsters)}</div>
            </div>
            <div class="monster-index-group">
                <p class="panel-label">외부</p>
                <div class="monster-index-list">${renderIndexLinks(outsideMonsters)}</div>
            </div>
            <div class="monster-index-group">
                <p class="panel-label">더미</p>
                <div class="monster-index-list">${renderIndexLinks(dummyMonsters)}</div>
            </div>
        </div>
        ${renderMonsterSection("INSIDE", "내부 몬스터", "시설 내부에서 조우하는 위협입니다. 시야 차단, 통로 구조, 근접 거리 관리가 핵심입니다.", insideMonsters)}
        ${renderMonsterSection("OUTSIDE", "외부 몬스터", "기지 귀환과 이동 동선에서 만나는 위협입니다. 소음, 개활지 노출, 우회 경로 정보가 중요합니다.", outsideMonsters)}
        ${renderMonsterSection("DUMMY", "더미 몬스터", "정식 분류와 별도로 확인된 더미 데이터입니다. 현재는 실전보다 참고용 성격이 큽니다.", dummyMonsters)}
    `;
}

function renderMonsterSection(label, title, copy, monsters) {
    const cards = monsters.map((monster) => renderMonsterCard(monster)).join("");

    return `
        <section class="monster-section">
            <div class="monster-section-heading">
                <div>
                    <p class="panel-label">${escapeHtml(label)}</p>
                    <h3 class="game-section-title">${escapeHtml(title)}</h3>
                </div>
                <p class="monster-section-copy">${escapeHtml(copy)}</p>
            </div>
            <div class="monster-card-list">${cards}</div>
        </section>
    `;
}

function renderIndexLinks(monsters) {
    return monsters
        .map((monster) => `
            <a class="tab-button monster-index-link" href="#monster-${escapeHtml(monster.id)}">
                <span class="monster-index-name">${escapeHtml(monster.name)}</span>
                <span class="monster-index-subname">${escapeHtml(monster.nameKr ?? "-")}</span>
                ${isDummyMonster(monster) ? '<span class="monster-index-flag">DUMMY</span>' : ""}
            </a>
        `)
        .join("");
}

function renderMonsterCard(monster) {
    const sectionTag = getMonsterSectionLabel(monster.section);
    const dummyTag = isDummyMonster(monster) ? '<span class="monster-tag monster-tag-dummy">DUMMY</span>' : "";

    return `
        <article class="monster-card pixel-box" id="monster-${escapeHtml(monster.id)}">
            <div class="monster-card-media">
                ${renderCardMedia(monster.image, monster.name)}
            </div>
            <div class="monster-card-copy">
                <div class="monster-card-header">
                    <div>
                        <p class="monster-card-kicker">${escapeHtml(sectionTag)} 몬스터</p>
                        <h3>${escapeHtml(monster.name)}</h3>
                        <p class="monster-card-subtitle">${escapeHtml(monster.nameKr ?? "-")}</p>
                    </div>
                    <div class="monster-card-tags">
                        <span class="monster-tag">${escapeHtml(sectionTag)}</span>
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

function renderRecordCard(category, group, entry) {
    const name = entry.name ?? entry.id;
    const subtitle = entry.nameKr ? `<p class="monster-card-subtitle">${escapeHtml(entry.nameKr)}</p>` : "";
    const priceLabel = category.id === "maps" ? "입장료" : "가격";
    const tags = [];
    const metaBlocks = [];

    if (group.label ?? group.title) {
        tags.push(`<span class="monster-tag">${escapeHtml(group.label ?? group.title)}</span>`);
    }
    if (entry.price !== undefined) {
        tags.push(`<span class="monster-tag monster-tag-accent">${escapeHtml(priceLabel)} ${escapeHtml(entry.price)}</span>`);
    }
    if (entry.terminalCommand) {
        tags.push(`<span class="monster-tag">${escapeHtml(entry.terminalCommand)}</span>`);
    }

    if (entry.description) {
        metaBlocks.push(renderMetaBlock("설명", entry.description, true));
    }
    if (entry.usage) {
        metaBlocks.push(renderMetaBlock("활용", entry.usage, true));
    }
    if (entry.spawnMonsters?.length) {
        const spawnMarkup = entry.spawnMonsters
            .map((monster) => `<li>${escapeHtml(monster.nameKr ?? monster.name ?? "-")}: ${escapeHtml(monster.chance ?? "-")}</li>`)
            .join("");
        metaBlocks.push(renderMetaBlock("주요 몬스터", `<ul>${spawnMarkup}</ul>`, true, true));
    }
    if (entry.installLink) {
        const installMarkup = /^https?:\/\//.test(entry.installLink)
            ? `<a href="${escapeHtml(entry.installLink)}" target="_blank" rel="noreferrer">설치 링크 열기</a>`
            : escapeHtml(entry.installLink);
        metaBlocks.push(renderMetaBlock("설치 링크", installMarkup, false, true));
    }

    metaBlocks.push(
        renderMetaBlock(
            "바로가기",
            `<a href="#${escapeHtml(category.id)}-${escapeHtml(entry.id)}">이 카드 위치</a>`,
            false,
            true,
        )
    );

    return `
        <article class="monster-card record-card pixel-box" id="${escapeHtml(category.id)}-${escapeHtml(entry.id)}">
            <div class="monster-card-media">
                ${renderCardMedia(entry.image, name)}
            </div>
            <div class="monster-card-copy">
                <div class="monster-card-header">
                    <div>
                        <p class="monster-card-kicker">${escapeHtml(category.label)} CARD</p>
                        <h3>${escapeHtml(name)}</h3>
                        ${subtitle}
                    </div>
                    <div class="monster-card-tags">${tags.join("")}</div>
                </div>
                <dl class="monster-meta-list">${metaBlocks.join("")}</dl>
            </div>
        </article>
    `;
}

function renderMetaBlock(label, value, wide = false, raw = false) {
    return `
        <div class="${wide ? "monster-meta-wide" : ""}">
            <dt>${escapeHtml(label)}</dt>
            <dd>${raw ? value : escapeHtml(value)}</dd>
        </div>
    `;
}

function renderCardMedia(image, alt) {
    if (image) {
        return `<img src="${escapeHtml(image)}" alt="${escapeHtml(alt)}">`;
    }

    return `<div class="monster-image-placeholder" aria-label="${escapeHtml(alt)} image unavailable">NO IMAGE</div>`;
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

function buildHashRoutes(data) {
    const routes = new Map();

    for (const tabId of ["guides", "install"]) {
        const categories = data[tabId] ?? [];

        categories.forEach((category) => {
            routes.set(category.id, { tabId, subtabId: category.id });

            (category.monsters ?? []).forEach((monster) => {
                routes.set(`monster-${monster.id}`, { tabId, subtabId: category.id });
            });

            (category.groups ?? []).forEach((group) => {
                (group.entries ?? []).forEach((entry) => {
                    routes.set(`${category.id}-${entry.id}`, { tabId, subtabId: category.id });
                });
            });
        });
    }

    return routes;
}

function applyHashState(hash, state, hashRoutes) {
    const route = hashRoutes.get(normalizeHash(hash));
    if (!route) {
        return false;
    }

    state.tabId = route.tabId;
    state.subtabId = route.subtabId;
    return true;
}

function bindHashNavigation(tabs, state, data, hashRoutes, tabList, subtabList, panel) {
    window.addEventListener("hashchange", () => {
        const routeMatched = applyHashState(window.location.hash, state, hashRoutes);
        if (routeMatched) {
            renderPage(tabs, state, data, tabList, subtabList, panel);
        }
        scrollToHashTarget(window.location.hash);
    });
}

function scrollToHashTarget(hash) {
    const targetId = normalizeHash(hash);
    if (!targetId) {
        return;
    }

    requestAnimationFrame(() => {
        const target = document.getElementById(targetId);
        if (!target) {
            return;
        }

        target.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    });
}

function normalizeHash(hash) {
    return String(hash ?? "").replace(/^#/, "");
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
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

loadGamePage();
