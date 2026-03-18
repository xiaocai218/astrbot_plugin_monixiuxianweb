const playerSelect = document.getElementById("player-select");
const playerCard = document.getElementById("player-card");
const rankingList = document.getElementById("ranking-list");
const worldStats = document.getElementById("world-stats");
const dbPath = document.getElementById("db-path");
const storageList = document.getElementById("storage-list");
const storageSummary = document.getElementById("storage-summary");
const inventorySummary = document.getElementById("inventory-summary");
const inventoryList = document.getElementById("inventory-list");
const shopList = document.getElementById("shop-list");
const riftRefresh = document.getElementById("rift-refresh");
const riftStatus = document.getElementById("rift-status");
const riftOpenList = document.getElementById("rift-open-list");
const riftClosedList = document.getElementById("rift-closed-list");
const bossRefresh = document.getElementById("boss-refresh");
const bossActive = document.getElementById("boss-active");
const bossHistory = document.getElementById("boss-history");
const bankOverview = document.getElementById("bank-overview");
const bankLoan = document.getElementById("bank-loan");
const bankTransactions = document.getElementById("bank-transactions");
const blessedLandCurrent = document.getElementById("blessed-land-current");
const blessedLandRules = document.getElementById("blessed-land-rules");
const blessedLandOptions = document.getElementById("blessed-land-options");
const adventureStatus = document.getElementById("adventure-status");
const adventureRoutes = document.getElementById("adventure-routes");
const spiritFarmCurrent = document.getElementById("spirit-farm-current");
const spiritFarmCrops = document.getElementById("spirit-farm-crops");
const spiritFarmHerbs = document.getElementById("spirit-farm-herbs");
const spiritEyeCurrent = document.getElementById("spirit-eye-current");
const spiritEyeList = document.getElementById("spirit-eye-list");
const dualCurrent = document.getElementById("dual-current");
const dualRules = document.getElementById("dual-rules");
const dualRequest = document.getElementById("dual-request");
const sectPlayer = document.getElementById("sect-player");
const sectRankingList = document.getElementById("sect-ranking-list");
const sectMembers = document.getElementById("sect-members");
const bountyActive = document.getElementById("bounty-active");
const bountyAvailable = document.getElementById("bounty-available");
const bountyRecent = document.getElementById("bounty-recent");
const tabs = Array.from(document.querySelectorAll(".tab"));
const shopTabs = Array.from(document.querySelectorAll(".shop-tab"));
const inventoryTabs = Array.from(document.querySelectorAll(".inventory-tab"));

let currentTab = "level";
let currentShopTab = "pill";
let currentInventoryTab = "equipment";
let currentDashboard = null;

function fillNodes(nodes, html) {
  nodes.filter(Boolean).forEach((node) => { node.innerHTML = html; });
}

async function fetchJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || `请求失败: ${response.status}`);
  return data;
}

function renderWorld(world) {
  worldStats.innerHTML = "";
  [["修士总数", world.player_count], ["宗门数量", world.sect_count], ["秘境数量", world.rift_count]].forEach(([label, value]) => {
    const card = document.createElement("article");
    card.className = "stat-card";
    card.innerHTML = `<span class="stat-label">${label}</span><strong class="stat-value">${value}</strong>`;
    worldStats.appendChild(card);
  });
}

function kvCard(label, value) {
  return `<article class="kv-card"><span class="kv-label">${label}</span><strong class="kv-value">${value}</strong></article>`;
}

function renderPlayer(player) {
  const resourceText = player.cultivation_type === "体修" ? `气血 ${player.blood_qi}/${player.max_blood_qi}` : `灵气 ${player.spiritual_qi}/${player.max_spiritual_qi}`;
  const bossStatus = player.boss_cooldown_remaining > 0
    ? `Boss冷却 ${Math.floor(player.boss_cooldown_remaining / 60)}分${player.boss_cooldown_remaining % 60}秒`
    : "Boss可挑战";
  const battleRecover = player.boss_hp_recovering ? "恢复中" : "已满血";
  playerCard.innerHTML = `
    <section class="player-header">
      <p class="eyebrow">角色总览</p>
      <h3>${player.name}</h3>
      <span class="pill">${player.level_name}</span>
      <p class="hero-text">${player.cultivation_type} · ${player.spiritual_root} · 当前状态 ${player.state}</p>
    </section>
    <section class="stats-grid">
      ${kvCard("灵石", player.gold.toLocaleString())}
      ${kvCard("修为", player.experience.toLocaleString())}
      ${kvCard("战斗HP", `${player.battle_hp}/${player.battle_hp_max}`)}
      ${kvCard("精神力", player.mental_power)}
    </section>
    <section class="detail-grid">
      ${kvCard("修炼资源", resourceText)}
      ${kvCard("战力", player.combat_power)}
      ${kvCard("寿命", player.lifespan)}
      ${kvCard("突破加成", `${player.level_up_rate}%`)}
      ${kvCard("物伤 / 法伤", `${player.physical_damage} / ${player.magic_damage}`)}
      ${kvCard("物防 / 法防", `${player.physical_defense} / ${player.magic_defense}`)}
      ${kvCard("Boss状态", bossStatus)}
      ${kvCard("HP恢复", battleRecover)}
      ${kvCard("宗门", player.sect_name)}
      ${kvCard("储物戒", `${player.storage_ring} · ${player.storage_count} 件`)}
    </section>
    <section class="equipment-grid">
      ${kvCard("主修功法", player.main_technique)}
      ${kvCard("法器", player.weapon)}
      ${kvCard("防具", player.armor)}
    </section>
    <section class="stats-grid">
      ${kvCard("丹药数量", player.pill_count)}
      ${kvCard("功法数量", player.techniques_count)}
      ${kvCard("战斗MP", player.mp)}
      ${kvCard("玩家ID", player.user_id)}
    </section>
  `;
}
function renderStorage(storageRing) {
  storageSummary.textContent = `槽位 ${storageRing.used_slots} · 物品 ${storageRing.total_items}`;
  storageList.innerHTML = storageRing.items.length ? storageRing.items.map((item) => `
    <article class="storage-row">
      <div><div class="storage-name">${item.name}</div><div class="storage-meta">储物戒物品</div></div>
      <div class="storage-count">x${item.count}</div>
      <div class="storage-bound">${item.bound ? "绑定" : "未绑定"}</div>
    </article>
  `).join("") : `<div class="empty">储物戒当前为空。</div>`;
}

function renderInventory(inventoryPreview) {
  inventorySummary.innerHTML = [
    kvCard("装备类", inventoryPreview.summary.equipment),
    kvCard("材料类", inventoryPreview.summary.material),
    kvCard("功法类", inventoryPreview.summary.technique),
    kvCard("其他类", inventoryPreview.summary.other),
    kvCard("丹药类", inventoryPreview.summary.pills),
  ].join("");

  const rows = currentInventoryTab === "pills"
    ? inventoryPreview.pills
    : inventoryPreview.categories[currentInventoryTab] || [];

  inventoryList.innerHTML = rows.length ? rows.map((item) => `
    <article class="inventory-row">
      <div class="inventory-head">
        <div class="inventory-name">${item.name}</div>
        <div class="inventory-count">x${item.count}</div>
      </div>
      <div class="inventory-meta">${item.rank} · ${item.type} · 需求境界索引 ${item.required_level_index}${item.bound ? ' · 绑定' : ''}</div>
      <div class="inventory-desc">${item.description || '暂无描述'}</div>
    </article>
  `).join("") : `<div class="empty">当前分类暂无物品。</div>`;
}

function formatRankingValue(tab, value) {
  if (tab === "wealth") return `${value.toLocaleString()} 灵石`;
  if (tab === "power") return `${value.toLocaleString()} 战力`;
  return `${value.toLocaleString()} 修为`;
}

function renderRankings() {
  const rows = currentDashboard ? currentDashboard.rankings[currentTab] || [] : [];
  rankingList.innerHTML = rows.length ? rows.map((row) => `
    <article class="ranking-row">
      <div class="rank-no">${row.rank}</div>
      <div><div class="rank-name">${row.name}</div><div class="rank-meta">${row.level_name}</div></div>
      <div class="rank-value">${formatRankingValue(currentTab, row.value)}</div>
    </article>
  `).join("") : `<div class="empty">暂无排行榜数据</div>`;
}

function renderShop() {
  const rows = currentDashboard ? currentDashboard.shop_preview[currentShopTab] || [] : [];
  shopList.innerHTML = rows.length ? rows.map((item) => `
    <article class="shop-row">
      <div class="shop-head"><div class="shop-name">${item.name}</div><div class="shop-price">${item.price.toLocaleString()} 灵石</div></div>
      <div class="shop-meta">${item.rank} · ${item.type} · 需求境界索引 ${item.required_level_index}</div>
      <div class="shop-desc">${item.description || "暂无描述"}</div>
    </article>
  `).join("") : `<div class="empty">当前分类暂无可展示数据</div>`;
}

function renderRifts(riftPreview) {
  riftRefresh.textContent = `约 ${riftPreview.next_refresh_in_minutes} 分钟后刷新`;
  riftStatus.innerHTML = riftPreview.player_status && riftPreview.player_status.is_exploring
    ? `<h3>玩家状态</h3><div class="rift-desc">当前玩家正在探索秘境中，目标秘境 ID 为 ${riftPreview.player_status.rift_id}，秘境等级 ${riftPreview.player_status.rift_level}。</div>`
    : `<h3>玩家状态</h3><div class="rift-desc">当前玩家未处于秘境探索状态，可在 Bot 端继续通过 /探索秘境 发起探索。</div>`;
  const renderList = (rows, isOpen) => rows.length ? rows.map((rift) => `
    <article class="rift-row">
      <div class="rift-head"><div class="rift-name">${rift.name}</div><div class="${isOpen ? "rift-state-open" : "rift-state-closed"}">${isOpen ? "本轮开放" : "暂未开放"}</div></div>
      <div class="rift-meta">ID ${rift.rift_id} · 等级 ${rift.rift_level} · 需求 ${rift.required_level_name}</div>
      <div class="rift-desc">修为奖励 ${rift.exp_range[0]}-${rift.exp_range[1]} · 灵石奖励 ${rift.gold_range[0]}-${rift.gold_range[1]}</div>
    </article>
  `).join("") : `<div class="empty">暂无数据</div>`;
  riftOpenList.innerHTML = renderList(riftPreview.open, true);
  riftClosedList.innerHTML = renderList(riftPreview.closed, false);
}

function renderBoss(bossPreview) {
  bossRefresh.textContent = `约 ${bossPreview.next_spawn_in_minutes} 分钟后刷新`;

  const skillList = bossPreview.enrage_skills.map((skill) => `
    <article class="boss-row">
      <div class="boss-head"><div class="boss-name">${skill.name}</div><div class="boss-state-live">狂暴技能</div></div>
      <div class="boss-desc">${skill.desc}</div>
    </article>
  `).join("");

  const playerStatusHtml = bossPreview.player_status ? `
    <article class="boss-row">
      <div class="boss-head"><div class="boss-name">玩家状态</div><div class="${bossPreview.player_status.can_challenge ? "boss-state-live" : "boss-state-dead"}">${bossPreview.player_status.can_challenge ? "可挑战" : "冷却中"}</div></div>
      <div class="boss-meta">战斗HP ${bossPreview.player_status.battle_hp}/${bossPreview.player_status.battle_hp_max} · ${bossPreview.player_status.battle_hp_percent}%</div>
      <div class="boss-desc">${bossPreview.player_status.cooldown_remaining > 0 ? `挑战冷却剩余 ${bossPreview.player_status.cooldown_remaining_minutes}分${bossPreview.player_status.cooldown_remaining_seconds}秒` : '当前可以挑战 Boss'} · ${bossPreview.player_status.recovery_desc}</div>
    </article>
  ` : `<div class="empty">当前玩家暂无 Boss 状态数据。</div>`;

  bossActive.innerHTML = bossPreview.active ? `
    <article class="boss-active-card">
      <div class="boss-head"><div class="boss-name">${bossPreview.active.name}</div><div class="${bossPreview.active.is_enrage_range ? "boss-state-dead" : "boss-state-live"}">${bossPreview.active.is_enrage_range ? `已进入 ${bossPreview.enrage_threshold_percent}% 狂暴线` : `未到 ${bossPreview.enrage_threshold_percent}% 狂暴线`}</div></div>
      <div class="boss-meta">境界 ${bossPreview.active.level} · ATK ${bossPreview.active.atk} · 减伤 ${bossPreview.active.defense}%</div>
      <div class="boss-desc">血量 ${bossPreview.active.hp}/${bossPreview.active.max_hp} · 血量占比 ${bossPreview.active.hp_percent}% · 击败奖励 ${bossPreview.active.stone_reward} 灵石</div>
      <div class="boss-desc">当 Boss 血量低于 ${bossPreview.enrage_threshold_percent}% 时，会随机触发一种持续 5 回合的狂暴技能。</div>
    </article>
    ${playerStatusHtml}
    <div class="subsection-title">狂暴技能</div>
    <div class="boss-history">${skillList}</div>
  ` : `<div class="empty">当前没有存活的世界 Boss。</div>${playerStatusHtml}<div class="subsection-title">狂暴技能</div><div class="boss-history">${skillList}</div>`;

  bossHistory.innerHTML = bossPreview.recent.length ? bossPreview.recent.map((boss) => `
    <article class="boss-row">
      <div class="boss-head"><div class="boss-name">${boss.name}</div><div class="${boss.status === 1 ? "boss-state-live" : "boss-state-dead"}">${boss.status === 1 ? "存活" : "已击败"}</div></div>
      <div class="boss-meta">境界 ${boss.level} · ATK ${boss.atk} · 减伤 ${boss.defense}%</div>
      <div class="boss-desc">血量 ${boss.hp}/${boss.max_hp} · 奖励 ${boss.stone_reward} 灵石</div>
    </article>
  `).join("") : `<div class="empty">暂无 Boss 历史记录。</div>`;
}
function renderBank(bankPreview) {
  bankOverview.innerHTML = [
    kvCard("\u5f53\u524d\u5883\u754c", bankPreview.level_name || "\u672a\u77e5"),
    kvCard("\u94f6\u884c\u5b58\u6b3e", bankPreview.balance.toLocaleString()),
    kvCard("\u5f53\u524d\u73b0\u91d1", bankPreview.cash.toLocaleString()),
    kvCard("\u603b\u8d44\u4ea7", bankPreview.total_assets.toLocaleString()),
    kvCard("\u666e\u901a\u8d37\u6b3e\u4e0a\u9650", bankPreview.normal_cap.toLocaleString()),
    kvCard("\u7a81\u7834\u8d37\u6b3e\u4e0a\u9650", bankPreview.breakthrough_cap.toLocaleString()),
    kvCard("\u5f85\u9886\u5229\u606f", bankPreview.pending_interest.toLocaleString()),
  ].join("");

  const breakthroughHint = bankPreview.breakthrough_pill_price
    ? `\u5f53\u524d\u7a81\u7834\u4e39\u53c2\u8003\u4ef7\u683c ${bankPreview.breakthrough_pill_price.toLocaleString()} \u7075\u77f3\uff0c\u7a81\u7834\u8d37\u6b3e\u6309\u5176\u7ea6 1.3 \u500d\u4f30\u7b97\u3002`
    : "\u5f53\u524d\u672a\u5339\u914d\u5230\u53ef\u7528\u7a81\u7834\u4e39\u4ef7\u683c\uff0c\u7a81\u7834\u8d37\u6b3e\u4f1a\u6309\u9ed8\u8ba4\u89c4\u5219\u9650\u5236\u3002";

  if (bankPreview.loan) {
    const loan = bankPreview.loan;
    const loanType = loan.loan_type === "breakthrough" ? "\u7a81\u7834\u8d37\u6b3e" : "\u666e\u901a\u8d37\u6b3e";
    const state = loan.is_overdue ? "\u5df2\u903e\u671f" : `\u5269\u4f59 ${loan.days_remaining} \u5929`;
    bankLoan.innerHTML = `
      <h3>\u8d37\u6b3e\u89c4\u5219</h3>
      <div class="bank-desc">\u666e\u901a\u8d37\u6b3e\u4f1a\u7ed3\u5408\u5f53\u524d\u5883\u754c\u6863\u4f4d\u4e0e\u603b\u8d44\u4ea7\u8fdb\u884c\u9650\u5236\uff0c\u907f\u514d\u524d\u671f\u989d\u5ea6\u8fc7\u9ad8\u6216\u540e\u671f\u989d\u5ea6\u5931\u771f\u3002</div>
      <div class="bank-desc">${breakthroughHint}</div>
      <div class="bank-desc">\u5f53\u524d\u5883\u754c\u4e0a\u9650 ${bankPreview.realm_cap.toLocaleString()}\uff0c\u672c\u6b21\u666e\u901a\u8d37\u6b3e\u53ef\u8d37\u4e0a\u9650 ${bankPreview.normal_cap.toLocaleString()} \u7075\u77f3\u3002</div>
      <h3>\u5f53\u524d\u8d37\u6b3e</h3>
      <div class="bank-desc">${loanType} \u00b7 \u672c\u91d1 ${loan.principal.toLocaleString()} \u7075\u77f3 \u00b7 \u5f53\u524d\u5229\u606f ${loan.current_interest.toLocaleString()} \u7075\u77f3 \u00b7 \u5e94\u8fd8 ${loan.total_due.toLocaleString()} \u7075\u77f3 \u00b7 ${state}</div>
    `;
  } else {
    bankLoan.innerHTML = `
      <h3>\u8d37\u6b3e\u89c4\u5219</h3>
      <div class="bank-desc">\u666e\u901a\u8d37\u6b3e\u4f1a\u7ed3\u5408\u5f53\u524d\u5883\u754c\u6863\u4f4d\u4e0e\u603b\u8d44\u4ea7\u8fdb\u884c\u9650\u5236\uff0c\u907f\u514d\u524d\u671f\u989d\u5ea6\u8fc7\u9ad8\u6216\u540e\u671f\u989d\u5ea6\u5931\u771f\u3002</div>
      <div class="bank-desc">${breakthroughHint}</div>
      <div class="bank-desc">\u5f53\u524d\u5883\u754c\u4e0a\u9650 ${bankPreview.realm_cap.toLocaleString()}\uff0c\u672c\u6b21\u666e\u901a\u8d37\u6b3e\u53ef\u8d37\u4e0a\u9650 ${bankPreview.normal_cap.toLocaleString()} \u7075\u77f3\u3002</div>
      <h3>\u5f53\u524d\u8d37\u6b3e</h3>
      <div class="bank-desc">\u5f53\u524d\u6ca1\u6709\u8fdb\u884c\u4e2d\u7684\u8d37\u6b3e\u3002</div>
    `;
  }

  bankTransactions.innerHTML = bankPreview.transactions.length ? bankPreview.transactions.map((trans) => `
    <article class="bank-row">
      <div class="bank-head"><div class="bank-name">${trans.description}</div><div class="bank-value">${trans.amount > 0 ? '+' : ''}${trans.amount.toLocaleString()}</div></div>
      <div class="bank-meta">\u7c7b\u578b ${trans.trans_type} \u00b7 \u53d8\u52a8\u540e\u4f59\u989d ${trans.balance_after.toLocaleString()} \u7075\u77f3</div>
    </article>
  `).join("") : `<div class="empty">\u6682\u65e0\u94f6\u884c\u6d41\u6c34\u8bb0\u5f55\u3002</div>`;
}

function renderBlessedLand(blessedLandPreview) {
  if (blessedLandPreview.current) {
    const land = blessedLandPreview.current;
    blessedLandCurrent.innerHTML = `
      <h3>\u5f53\u524d\u6d1e\u5929</h3>
      <div class="bank-desc">\u5f53\u524d\u62e5\u6709 <strong>${land.name}</strong>\uff0c\u7b49\u7ea7 Lv.${land.level}\u3002</div>
      <div class="bank-desc">\u4fee\u70bc\u52a0\u6210 ${land.exp_bonus_percent}% \u00b7 \u6bcf\u5c0f\u65f6\u7075\u77f3\u4ea7\u51fa ${land.gold_per_hour.toLocaleString()}\u3002</div>
      <div class="bank-desc">\u76f8\u5173\u64cd\u4f5c\u4ecd\u901a\u8fc7 Bot \u6307\u4ee4\u6267\u884c\uff1a/\u6211\u7684\u6d1e\u5929\u3001/\u5347\u7ea7\u6d1e\u5929\u3001/\u6d1e\u5929\u6536\u53d6\u3002</div>
    `;
  } else {
    blessedLandCurrent.innerHTML = `
      <h3>\u5f53\u524d\u6d1e\u5929</h3>
      <div class="bank-desc">${blessedLandPreview.empty_state}</div>
    `;
  }

  blessedLandRules.innerHTML = `
    <h3>\u7f6e\u6362\u89c4\u5219</h3>
    <div class="bank-desc">\u5f53\u524d Web \u7aef\u53ea\u5c55\u793a\u89c4\u5219\u4e0e\u72b6\u6001\uff0c\u5b9e\u9645\u64cd\u4f5c\u4ecd\u9700\u901a\u8fc7 Bot \u6307\u4ee4\u5b8c\u6210\u3002</div>
    <div class="bank-desc">\u5df2\u6709\u6d1e\u5929\u540e\uff0c\u53ef\u4f7f\u7528 /\u7f6e\u6362\u6d1e\u5929 &lt;\u7f16\u53f7&gt; \u66f4\u6362\u6d1e\u5929\u7c7b\u578b\u3002</div>
    <div class="bank-desc">\u65e7\u6d1e\u5929\u6309\u539f\u4ef7 ${(blessedLandPreview.replace_credit_rate * 100).toFixed(0)}% \u6298\u7b97\u62b5\u6263\uff0c\u65b0\u6d1e\u5929\u4f1a\u6309\u73b0\u6709\u7b49\u7ea7\u548c\u4e0a\u9650\u91cd\u65b0\u7ed3\u7b97\u3002</div>
    <div class="bank-desc">\u7f6e\u6362\u540e\u4f1a\u91cd\u7f6e\u6536\u53d6\u65f6\u95f4\uff0c\u907f\u514d\u91cd\u590d\u9886\u53d6\u4ea7\u51fa\u3002</div>
  `;

  blessedLandOptions.innerHTML = blessedLandPreview.options.length ? blessedLandPreview.options.map((item) => `
    <article class="shop-row">
      <div class="shop-head"><div class="shop-name">${item.type}. ${item.name}</div><div class="shop-price">${item.price.toLocaleString()} \u7075\u77f3</div></div>
      <div class="shop-desc">Bot \u6307\u4ee4\uff1a${blessedLandPreview.current ? `/\u7f6e\u6362\u6d1e\u5929 ${item.type}` : `/\u8d2d\u4e70\u6d1e\u5929 ${item.type}`}</div>
    </article>
  `).join("") : `<div class="empty">\u6682\u65e0\u53ef\u5c55\u793a\u7684\u6d1e\u5929\u914d\u7f6e\u3002</div>`;
}

function renderAdventure(adventurePreview) {
  if (adventurePreview.active) {
    const active = adventurePreview.active;
    const completeText = active.is_complete ? "\u5df2\u5b8c\u6210\uff0c\u53ef\u901a\u8fc7 /\u5b8c\u6210\u5386\u7ec3 \u9886\u53d6\u5956\u52b1" : `\u5269\u4f59 ${active.remaining_minutes} \u5206\u949f`;
    adventureStatus.innerHTML = `
      <h3>\u5f53\u524d\u5386\u7ec3</h3>
      <div class="bank-desc">\u5f53\u524d\u6b63\u5728\u5386\u7ec3\u8def\u7ebf <strong>${active.route_name}</strong>\uff0c\u98ce\u9669\u7b49\u7ea7 ${active.risk}\u3002</div>
      <div class="bank-desc">\u5df2\u8fdb\u884c ${active.elapsed_minutes} \u5206\u949f\uff0c${completeText}</div>
    `;
  } else {
    adventureStatus.innerHTML = `
      <h3>\u5f53\u524d\u5386\u7ec3</h3>
      <div class="bank-desc">${adventurePreview.empty_state}</div>
    `;
  }

  adventureRoutes.innerHTML = adventurePreview.routes.length ? adventurePreview.routes.map((route) => `
    <article class="shop-row">
      <div class="shop-head"><div class="shop-name">${route.name}</div><div class="shop-price">${route.duration_minutes} \u5206\u949f</div></div>
      <div class="shop-meta">\u98ce\u9669 ${route.risk} \u00b7 \u9700\u6c42\u5883\u754c\u7d22\u5f15 ${route.min_level} \u00b7 \u60ac\u8d4f\u6807\u7b7e ${route.bounty_tag}</div>
      <div class="shop-desc">${route.description || '\u6682\u65e0\u63cf\u8ff0'} \u00b7 Bot \u6307\u4ee4\uff1a/\u5f00\u59cb\u5386\u7ec3 ${route.name}</div>
    </article>
  `).join("") : `<div class="empty">\u5f53\u524d\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u5386\u7ec3\u8def\u7ebf\u3002</div>`;
}


function renderSpiritFarm(spiritFarmPreview) {
  if (spiritFarmPreview.current) {
    const farm = spiritFarmPreview.current;
    const upgradeText = farm.is_max_level
      ? "\u7075\u7530\u5df2\u8fbe\u6700\u9ad8\u7ea7"
      : `\u4e0b\u4e00\u7ea7\u683c\u6570 ${farm.next_slots} \u683c \u00b7 \u5347\u7ea7\u9700\u8981 ${farm.next_upgrade_cost.toLocaleString()} \u7075\u77f3`;
    spiritFarmCurrent.innerHTML = `
      <h3>\u5f53\u524d\u7075\u7530</h3>
      <div class="bank-desc">\u7075\u7530\u7b49\u7ea7 Lv.${farm.level} \u00b7 \u5df2\u7528 ${farm.used_slots}/${farm.slots} \u683c</div>
      <div class="bank-desc">${upgradeText}</div>
      <div class="bank-desc">\u76f8\u5173\u64cd\u4f5c\u4ecd\u901a\u8fc7 Bot \u6307\u4ee4\u6267\u884c\uff1a/\u5f00\u57a6\u7075\u7530\u3001/\u79cd\u690d\u3001/\u6536\u83b7\u3001/\u5347\u7ea7\u7075\u7530\u3002</div>
    `;
  } else {
    spiritFarmCurrent.innerHTML = `
      <h3>\u5f53\u524d\u7075\u7530</h3>
      <div class="bank-desc">${spiritFarmPreview.empty_state}</div>
    `;
  }

  spiritFarmCrops.innerHTML = spiritFarmPreview.crops.length ? spiritFarmPreview.crops.map((crop) => {
    const stateText = crop.state === "growing"
      ? "\u751f\u957f\u4e2d"
      : crop.state === "mature"
        ? "\u5df2\u6210\u719f"
        : "\u5df2\u67af\u840e";
    return `
      <article class="shop-row">
        <div class="shop-head"><div class="shop-name">${crop.name}</div><div class="shop-price">${stateText}</div></div>
        <div class="shop-meta">\u4ea7\u51fa ${crop.exp_yield.toLocaleString()} \u4fee\u4e3a \u00b7 ${crop.gold_yield.toLocaleString()} \u7075\u77f3</div>
        <div class="shop-desc">${crop.status_text}</div>
      </article>
    `;
  }).join("") : `<div class="empty">\u5f53\u524d\u7075\u7530\u8fd8\u6ca1\u6709\u79cd\u690d\u4efb\u4f55\u7075\u8349\u3002</div>`;

  spiritFarmHerbs.innerHTML = spiritFarmPreview.herbs.length ? spiritFarmPreview.herbs.map((herb) => `
    <article class="shop-row">
      <div class="shop-head"><div class="shop-name">${herb.name}</div><div class="shop-price">${herb.grow_minutes} \u5206\u949f</div></div>
      <div class="shop-meta">\u6536\u76ca ${herb.exp_yield.toLocaleString()} \u4fee\u4e3a \u00b7 ${herb.gold_yield.toLocaleString()} \u7075\u77f3</div>
      <div class="shop-desc">Bot \u6307\u4ee4\uff1a/\u79cd\u690d ${herb.name}</div>
    </article>
  `).join("") : `<div class="empty">\u5f53\u524d\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u7075\u8349\u914d\u7f6e\u3002</div>`;
}


function renderSpiritEye(spiritEyePreview) {
  const refreshText = spiritEyePreview.next_refresh_in_minutes == null
    ? "\u6682\u65e0\u5237\u65b0\u5012\u8ba1\u65f6\u6570\u636e"
    : `\u7ea6 ${spiritEyePreview.next_refresh_in_minutes} \u5206\u949f\u540e\u5237\u65b0\u65b0\u7075\u773c`;

  if (spiritEyePreview.current) {
    const eye = spiritEyePreview.current;
    spiritEyeCurrent.innerHTML = `
      <h3>\u6211\u7684\u7075\u773c</h3>
      <div class="bank-desc">\u5f53\u524d\u5360\u636e <strong>${eye.name}</strong>\uff08ID ${eye.eye_id}\uff09\uff0c\u6bcf\u5c0f\u65f6 +${eye.exp_per_hour.toLocaleString()} \u4fee\u4e3a\u3002</div>
      <div class="bank-desc">\u5f85\u6536\u53d6\u7ea6 +${eye.pending_exp.toLocaleString()} \u4fee\u4e3a \u00b7 \u5df2\u5360\u636e ${eye.claim_minutes} \u5206\u949f</div>
      <div class="bank-desc">${refreshText} \u00b7 Bot \u6307\u4ee4\uff1a/\u7075\u773c\u6536\u53d6 \u3001 /\u91ca\u653e\u7075\u773c</div>
    `;
  } else {
    spiritEyeCurrent.innerHTML = `
      <h3>\u6211\u7684\u7075\u773c</h3>
      <div class="bank-desc">\u5f53\u524d\u8fd8\u6ca1\u6709\u5360\u636e\u7075\u773c\u3002</div>
      <div class="bank-desc">${refreshText} \u00b7 Bot \u6307\u4ee4\uff1a/\u7075\u773c\u4fe1\u606f \u3001 /\u62a2\u5360\u7075\u773c &lt;ID&gt;</div>
    `;
  }

  spiritEyeList.innerHTML = spiritEyePreview.eyes.length ? spiritEyePreview.eyes.map((eye) => `
    <article class="shop-row">
      <div class="shop-head"><div class="shop-name">[${eye.eye_id}] ${eye.name}</div><div class="shop-price">+${eye.exp_per_hour.toLocaleString()} / \u5c0f\u65f6</div></div>
      <div class="shop-meta">${eye.is_owned ? `\u5f52\u5c5e ${eye.owner_name}` : '\u5f53\u524d\u65e0\u4e3b'}</div>
      <div class="shop-desc">\u5f85\u7ed3\u7b97\u7ea6 +${eye.pending_exp.toLocaleString()} \u4fee\u4e3a \u00b7 Bot \u6307\u4ee4\uff1a/\u62a2\u5360\u7075\u773c ${eye.eye_id}${eye.is_owned ? ' \u786e\u8ba4' : ''}</div>
    </article>
  `).join("") : `<div class="empty">${spiritEyePreview.empty_state}</div>`;
}

function renderDualCultivation(dualPreview) {
  if (dualPreview.cooldown_minutes > 0) {
    dualCurrent.innerHTML = `
      <h3>当前状态</h3>
      <div class="bank-desc">当前处于双修冷却中，还需等待 ${dualPreview.cooldown_minutes} 分钟才能再次发起或接受双修。</div>
    `;
  } else if (dualPreview.last_dual_at) {
    dualCurrent.innerHTML = `
      <h3>当前状态</h3>
      <div class="bank-desc">最近完成过一次双修，目前不在冷却中，可继续通过 Bot 指令发起新的双修请求。</div>
    `;
  } else {
    dualCurrent.innerHTML = `
      <h3>当前状态</h3>
      <div class="bank-desc">当前还没有双修记录，可以主动向其他玩家发起双修邀请。</div>
    `;
  }

  dualRules.innerHTML = `
    <h3>双修规则</h3>
    <div class="bank-desc">双方修为差距不能超过 ${dualPreview.max_exp_ratio} 倍，双修成功后双方都会获得对方 ${dualPreview.exp_bonus_percent}% 的修为收益。</div>
    <div class="bank-desc">双修完成后会进入 ${dualPreview.cooldown_hours} 小时冷却，请求发出后 ${dualPreview.request_expire_minutes} 分钟内有效。</div>
    <div class="bank-desc">请继续使用 Bot 指令：/双修 @某人、/接受双修、/拒绝双修。</div>
  `;

  if (dualPreview.pending_request) {
    const request = dualPreview.pending_request;
    dualRequest.innerHTML = `
      <article class="shop-row">
        <div class="shop-head"><div class="shop-name">来自 ${request.from_name} 的双修请求</div><div class="shop-price">${request.expires_in_minutes} 分钟后过期</div></div>
        <div class="shop-meta">${request.level_name} · 修为 ${request.experience.toLocaleString()}</div>
        <div class="shop-desc">请在 Bot 端使用 /接受双修 或 /拒绝双修 进行处理。</div>
      </article>
    `;
  } else {
    dualRequest.innerHTML = `<div class="empty">${dualPreview.empty_state}</div>`;
  }
}
function renderSect(sectPreview) {
  if (sectPreview.player_sect) {
    const sect = sectPreview.player_sect;
    sectPlayer.innerHTML = `
      <h3>当前宗门</h3>
      <div class="sect-desc">你当前所在宗门为 <strong>${sect.name}</strong>，职位 ${sect.player_position_name}，个人贡献 ${sect.player_contribution.toLocaleString()}。</div>
      <div class="sect-desc">宗主 ${sect.owner_name} · 建设度 ${sect.scale.toLocaleString()} · 灵石 ${sect.used_stone.toLocaleString()} · 资材 ${sect.materials.toLocaleString()} · 成员 ${sect.member_count} 人。</div>
      <div class="sect-desc">洞天等级 ${sect.fairyland} · 主修加成 ${sect.mainbuff} · 辅修加成 ${sect.secbuff} · 丹房等级 ${sect.elixir_room_level}。</div>
    `;
    sectMembers.innerHTML = sect.members.length ? sect.members.map((member) => `
      <article class="sect-row">
        <div class="sect-head"><div class="sect-name">${member.name}</div><div class="sect-rank">${member.position_name}</div></div>
        <div class="sect-meta">${member.level_name} · 贡献 ${member.contribution.toLocaleString()}</div>
      </article>
    `).join("") : `<div class="empty">当前宗门还没有可展示的成员信息。</div>`;
  } else {
    sectPlayer.innerHTML = `<h3>当前宗门</h3><div class="sect-desc">当前玩家尚未加入宗门。</div>`;
    sectMembers.innerHTML = `<div class="empty">当前玩家没有宗门成员列表可展示。</div>`;
  }

  sectRankingList.innerHTML = sectPreview.rankings.length ? sectPreview.rankings.map((sect) => `
    <article class="sect-row">
      <div class="sect-head"><div class="sect-name">#${sect.rank} ${sect.name}</div><div class="sect-rank">${sect.member_count} 人</div></div>
      <div class="sect-meta">宗主 ${sect.owner_name} · 建设度 ${sect.scale.toLocaleString()} · 资材 ${sect.materials.toLocaleString()} · 灵石 ${sect.used_stone.toLocaleString()} · 洞天等级 ${sect.fairyland}</div>
    </article>
  `).join("") : `<div class="empty">${sectPreview.empty_state}</div>`;
}


function renderBounty(bountyPreview) {
  if (bountyPreview.active) {
    const active = bountyPreview.active;
    bountyActive.innerHTML = `
      <h3>\u5f53\u524d\u60ac\u8d4f</h3>
      <div class="bounty-desc">\u4efb\u52a1 ${active.name} \u00b7 ${active.difficulty_name} \u00b7 \u8fdb\u5ea6 ${active.current_progress}/${active.target_count} \u00b7 \u5269\u4f59 ${active.remaining_minutes} \u5206\u949f</div>
      <div class="bounty-desc">\u5956\u52b1 ${active.stone_reward.toLocaleString()} \u7075\u77f3 + ${active.exp_reward.toLocaleString()} \u4fee\u4e3a \u00b7 \u76ee\u6807 ${active.target_type}</div>
      <div class="bounty-desc">${active.description || '\u6682\u65e0\u4efb\u52a1\u8bf4\u660e\u3002'}</div>
    `;
  } else if (bountyPreview.accept_cooldown_minutes > 0) {
    bountyActive.innerHTML = `
      <h3>\u5f53\u524d\u60ac\u8d4f</h3>
      <div class="bounty-desc">\u5f53\u524d\u5904\u4e8e\u63a5\u53d6\u51b7\u5374\u4e2d\uff0c\u8fd8\u9700\u7b49\u5f85 ${bountyPreview.accept_cooldown_minutes} \u5206\u949f\u624d\u80fd\u518d\u6b21\u63a5\u53d6\u60ac\u8d4f\u3002</div>
    `;
  } else {
    bountyActive.innerHTML = `
      <h3>\u5f53\u524d\u60ac\u8d4f</h3>
      <div class="bounty-desc">\u5f53\u524d\u6ca1\u6709\u8fdb\u884c\u4e2d\u7684\u60ac\u8d4f\uff0c\u53ef\u901a\u8fc7 Bot \u6307\u4ee4 /\u60ac\u8d4f\u4efb\u52a1 \u67e5\u770b\u5e76\u63a5\u53d6\u3002</div>
    `;
  }

  bountyAvailable.innerHTML = bountyPreview.available.length ? bountyPreview.available.map((item) => `
    <article class="bounty-row">
      <div class="bounty-head"><div class="bounty-name">[${item.id}] ${item.name}</div><div class="bounty-rank">${item.difficulty_name}</div></div>
      <div class="bounty-meta">\u5206\u7c7b ${item.category} \u00b7 \u76ee\u6807 ${item.min_target}-${item.max_target} \u6b21 \u00b7 \u65f6\u9650 ${item.time_limit_minutes} \u5206\u949f</div>
      <div class="bounty-desc">\u5956\u52b1 ${item.stone_reward.toLocaleString()} \u7075\u77f3 + ${item.exp_reward.toLocaleString()} \u4fee\u4e3a \u00b7 \u6807\u7b7e ${item.progress_tags.join(', ') || '\u65e0'}</div>
      <div class="bounty-desc">${item.description || '\u6682\u65e0\u8bf4\u660e'}</div>
    </article>
  `).join("") : `<div class="empty">\u5f53\u524d\u6ca1\u6709\u53ef\u63a5\u60ac\u8d4f\u6a21\u677f\u3002</div>`;

  bountyRecent.innerHTML = bountyPreview.recent.length ? bountyPreview.recent.map((item) => `
    <article class="bounty-row">
      <div class="bounty-head"><div class="bounty-name">[${item.bounty_id}] ${item.name}</div><div class="bounty-rank">${item.status_name}</div></div>
      <div class="bounty-meta">\u76ee\u6807 ${item.target_type} \u00b7 \u8fdb\u5ea6 ${item.current_progress}/${item.target_count}</div>
    </article>
  `).join("") : `<div class="empty">${bountyPreview.empty_state}</div>`;
}


async function loadDashboard(userId) {
  const loading = `<div class="empty">正在载入数据...</div>`;
  fillNodes([playerCard, storageList, inventorySummary, inventoryList, shopList, rankingList, riftOpenList, riftClosedList, bossActive, bossHistory, bankOverview, bankTransactions, blessedLandCurrent, blessedLandRules, blessedLandOptions, adventureStatus, adventureRoutes, spiritFarmCurrent, spiritFarmCrops, spiritFarmHerbs, spiritEyeCurrent, spiritEyeList, dualCurrent, dualRules, dualRequest, sectPlayer, sectRankingList, sectMembers, bountyActive, bountyAvailable, bountyRecent], loading);
  bankLoan.innerHTML = loading;
  try {
    const data = await fetchJson(`/api/dashboard?user_id=${encodeURIComponent(userId)}`);
    currentDashboard = data;
    renderPlayer(data.player);
    renderStorage(data.storage_ring);
    renderInventory(data.inventory_preview);
    renderShop();
    renderRankings();
    renderRifts(data.rift_preview);
    renderBoss(data.boss_preview);
    renderBank(data.bank_preview);
    renderBlessedLand(data.blessed_land_preview);
    renderAdventure(data.adventure_preview);
    renderSpiritFarm(data.spirit_farm_preview);
    renderSpiritEye(data.spirit_eye_preview);
    renderDualCultivation(data.dual_cultivation_preview);
    renderSect(data.sect_preview);
    renderBounty(data.bounty_preview);
  } catch (error) {
    const html = `<div class="error">${error.message}</div>`;
    fillNodes([playerCard, storageList, inventorySummary, inventoryList, shopList, rankingList, riftOpenList, riftClosedList, bossActive, bossHistory, bankOverview, bankTransactions, blessedLandCurrent, blessedLandRules, blessedLandOptions, adventureStatus, adventureRoutes, spiritFarmCurrent, spiritFarmCrops, spiritFarmHerbs, spiritEyeCurrent, spiritEyeList, dualCurrent, dualRules, dualRequest, sectPlayer, sectRankingList, sectMembers, bountyActive, bountyAvailable, bountyRecent], html);
    bankLoan.innerHTML = html;
  }
}

async function bootstrap() {
  try {
    const health = await fetchJson("/api/health");
    dbPath.textContent = `数据库：${health.db_path}`;
    const data = await fetchJson("/api/players");
    renderWorld(data.world);
    if (!data.players.length) {
      playerSelect.innerHTML = `<option value="">暂无玩家</option>`;
      const html = `<div class="empty">当前数据库中还没有玩家数据。</div>`;
      fillNodes([playerCard, storageList, inventorySummary, inventoryList, shopList, rankingList, riftOpenList, riftClosedList, bossActive, bossHistory, bankOverview, bankTransactions, blessedLandCurrent, blessedLandRules, blessedLandOptions, adventureStatus, adventureRoutes, spiritFarmCurrent, spiritFarmCrops, spiritFarmHerbs, spiritEyeCurrent, spiritEyeList, dualCurrent, dualRules, dualRequest, sectPlayer, sectRankingList, sectMembers, bountyActive, bountyAvailable, bountyRecent], html);
      bankLoan.innerHTML = html;
      return;
    }
    playerSelect.innerHTML = data.players.map((player) => `<option value="${player.user_id}">${player.name} · ${player.level_name} · ${player.cultivation_type}</option>`).join("");
    await loadDashboard(playerSelect.value);
  } catch (error) {
    const html = `<div class="error">${error.message}</div>`;
    fillNodes([playerCard, storageList, inventorySummary, inventoryList, shopList, rankingList, riftOpenList, riftClosedList, bossActive, bossHistory, bankOverview, bankTransactions, blessedLandCurrent, blessedLandRules, blessedLandOptions, adventureStatus, adventureRoutes, spiritFarmCurrent, spiritFarmCrops, spiritFarmHerbs, spiritEyeCurrent, spiritEyeList, dualCurrent, dualRules, dualRequest, sectPlayer, sectRankingList, sectMembers, bountyActive, bountyAvailable, bountyRecent], html);
    bankLoan.innerHTML = html;
  }
}

playerSelect.addEventListener("change", () => { if (playerSelect.value) loadDashboard(playerSelect.value); });
tabs.forEach((tab) => tab.addEventListener("click", () => { tabs.forEach((item) => item.classList.remove("is-active")); tab.classList.add("is-active"); currentTab = tab.dataset.tab; renderRankings(); }));
shopTabs.forEach((tab) => tab.addEventListener("click", () => { shopTabs.forEach((item) => item.classList.remove("is-active")); tab.classList.add("is-active"); currentShopTab = tab.dataset.shopTab; renderShop(); }));
inventoryTabs.forEach((tab) => tab.addEventListener("click", () => { inventoryTabs.forEach((item) => item.classList.remove("is-active")); tab.classList.add("is-active"); currentInventoryTab = tab.dataset.inventoryTab; if (currentDashboard) renderInventory(currentDashboard.inventory_preview); }));
bootstrap();
