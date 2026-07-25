(function initializeSite() {
    const config = window.YEONSAM_SITE_CONFIG ?? {};
    const installLink = document.getElementById("install-bot-link");
    const installHelp = document.getElementById("install-help");
    const applicationId = String(config.discordApplicationId ?? "").trim();

    if (installLink && /^\d{15,25}$/.test(applicationId)) {
        const query = new URLSearchParams({
            client_id: applicationId,
            scope: "bot applications.commands",
            permissions: "134269952"
        });
        installLink.href = `https://discord.com/oauth2/authorize?${query.toString()}`;
        installLink.textContent = "Discord에 연삼이 추가";
        installLink.classList.remove("is-disabled");
        installLink.removeAttribute("aria-disabled");
        if (installHelp) {
            installHelp.textContent = "채널 보기·메시지·임베드·파일 첨부·닉네임 관리 권한만 요청합니다.";
        }
    }

    const supportUrl = String(config.supportUrl ?? "").trim();
    if (/^https:\/\//.test(supportUrl)) {
        document.querySelectorAll("[data-support-link]").forEach((link) => {
            link.href = supportUrl;
        });
    }

    const statusNode = document.getElementById("service-status");
    const statusDetail = document.getElementById("service-status-detail");
    const healthUrl = String(config.botHealthUrl ?? "").trim();
    if (!statusNode || !statusDetail) {
        return;
    }
    if (!/^https:\/\//.test(healthUrl)) {
        statusNode.textContent = "모니터링 주소 미설정";
        statusNode.dataset.state = "unknown";
        statusDetail.textContent = "운영 배포에서 BOT_HEALTH_URL을 설정하면 실시간 상태를 확인할 수 있습니다.";
        return;
    }

    fetch(healthUrl, { cache: "no-store" })
        .then((response) => response.json().then((payload) => ({ response, payload })))
        .then(({ response, payload }) => {
            if (response.ok && payload.ready === true) {
                statusNode.textContent = "정상 운영 중";
                statusNode.dataset.state = "online";
                statusDetail.textContent = "Discord 연결과 봇 프로세스가 정상입니다.";
                return;
            }
            throw new Error("Bot is not ready");
        })
        .catch(() => {
            statusNode.textContent = "상태 확인 실패";
            statusNode.dataset.state = "offline";
            statusDetail.textContent = "봇이 시작 중이거나 상태 서버에 연결할 수 없습니다.";
        });
})();
