const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let cache = {clients:[],products:[],movements:[],debts:[]};
let movementFilter='all', debtFilter='all';
let deferredInstallPrompt = null;

const money = v => Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const num = v => Number(v||0).toLocaleString('pt-BR',{maximumFractionDigits:2});
const dateBR = d => d ? new Date(d+'T12:00:00').toLocaleDateString('pt-BR') : '—';
const esc = s => String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const ico = id => `<svg aria-hidden="true"><use href="#${id}"/></svg>`;
const initials = name => String(name||'?').trim().split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase();

async function api(url,opts={}){
  const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});
  const data=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(data.error||'Não foi possível concluir.');
  return data;
}
function toast(msg,error=false){const t=$('#toast');t.textContent=msg;t.className='toast show'+(error?' error':'');clearTimeout(window._toast);window._toast=setTimeout(()=>t.className='toast',2600)}
function closeModal(){ $('#modal').classList.add('hidden'); document.body.style.overflow=''; }
function showModal(html){$('#modalContent').innerHTML=html;$('#modal').classList.remove('hidden');document.body.style.overflow='hidden'}

const titles={dashboard:'Visão geral',movements:'Entrada e saída',clients:'Clientes e fornecedores',stock:'Estoque',debts:'Saldo devedor'};
function setMobileAction(name){
  const fab=$('#mobileFab');
  if(!fab) return;
  const actions={dashboard:()=>openMovementModal(),movements:()=>openMovementModal(),clients:()=>openClientModal(),stock:()=>openProductModal(),debts:()=>openDebtModal()};
  const labels={dashboard:'Nova movimentação',movements:'Nova movimentação',clients:'Novo cliente',stock:'Novo item',debts:'Novo saldo'};
  fab.onclick=actions[name]||actions.dashboard;
  fab.setAttribute('aria-label',labels[name]||'Adicionar');
  fab.title=labels[name]||'Adicionar';
}
function goPage(name){
  $$('.page').forEach(p=>p.classList.remove('active'));
  $('#page-'+name)?.classList.add('active');
  $$('.nav-btn[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===name));
  $('#pageTitle').textContent=titles[name]||'Rocha Café';
  setMobileAction(name);
  if(window.innerWidth<=900) window.scrollTo({top:0,behavior:'smooth'});
  if(name==='dashboard') loadDashboard();
  if(name==='movements') loadMovements();
  if(name==='clients') loadClients();
  if(name==='stock') loadProducts();
  if(name==='debts') loadDebts();
}
$$('.nav-btn[data-page]').forEach(b=>b.onclick=()=>goPage(b.dataset.page));
$('#quickMovement').onclick=()=>openMovementModal();

function setToday(){
  const now=new Date();
  const el=$('#todayLabel');
  if(el) el.textContent=new Intl.DateTimeFormat('pt-BR',{weekday:'short',day:'2-digit',month:'short'}).format(now).replaceAll('.','');
  const month=$('#currentMonthLabel');
  if(month) month.textContent=new Intl.DateTimeFormat('pt-BR',{month:'long',year:'numeric'}).format(now).replace(/^./,c=>c.toUpperCase());
  const greeting=$('#greetingTitle');
  if(greeting){
    const h=now.getHours();
    const part=h<12?'Bom dia':h<18?'Boa tarde':'Boa noite';
    greeting.innerHTML=`${part}. <span>O negócio está na sua mão.</span>`;
  }
}

function compactMoney(v){
  const n=Number(v||0);
  if(Math.abs(n)>=1000000) return 'R$ '+(n/1000000).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mi';
  if(Math.abs(n)>=1000) return 'R$ '+(n/1000).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mil';
  return money(n);
}

function renderExecutiveChart(series=[]){
  const el=$('#executiveChart'); if(!el) return;
  if(!series.length){el.innerHTML='<div class="chart-empty">O gráfico aparece após as primeiras movimentações.</div>';return}
  const max=Math.max(1,...series.flatMap(x=>[Number(x.sales||0),Number(x.purchases||0)]));
  const monthName=k=>new Intl.DateTimeFormat('pt-BR',{month:'short'}).format(new Date(k+'-02T12:00:00')).replace('.','').toUpperCase();
  el.innerHTML=series.map(x=>{
    const sh=Math.max(3,Math.round(Number(x.sales||0)/max*100));
    const ph=Math.max(3,Math.round(Number(x.purchases||0)/max*100));
    return `<div class="chart-month" title="${monthName(x.month)} · Vendas ${money(x.sales)} · Compras ${money(x.purchases)}"><div class="chart-bars"><i class="bar sales" style="height:${sh}%"></i><i class="bar purchases" style="height:${ph}%"></i></div><span>${monthName(x.month)}</span></div>`;
  }).join('');
  const pulse=$('#heroPulse');
  if(pulse) pulse.innerHTML=series.map(x=>{const h=Math.max(8,Math.round(Number(x.sales||0)/max*100));return `<i style="height:${h}%"></i>`}).join('');
}

function openMonthlyReport(){
  const current=new Date().toISOString().slice(0,7);
  showModal(`<div class="modal-premium-head"><span class="premium-seal big">${ico('i-file')}</span><div><h2>Relatório executivo</h2><p class="sub">Escolha o mês e abra uma versão pronta para imprimir ou salvar em PDF.</p></div></div><div class="report-picker"><label>MÊS DO RELATÓRIO</label><input id="reportMonth" type="month" value="${current}"><div class="report-preview"><span>${ico('i-chart')}</span><div><strong>Resumo completo do período</strong><small>Compras, vendas, estoque, saldos e todas as movimentações.</small></div></div></div><div class="modal-actions"><button class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary" onclick="window.open('/relatorio/mensal?month='+encodeURIComponent($('#reportMonth').value),'_blank');closeModal()">Abrir relatório</button></div>`);
}

async function loadDashboard(){
  try{
    const d=await api('/api/dashboard');
    $('#dStockQty').textContent=num(d.stock_quantity);
    $('#dStockValue').textContent=money(d.stock_value);
    $('#dReceive').textContent=money(d.to_receive);
    $('#dPay').textContent=money(d.to_pay);
    $('#dProducts').textContent=`${d.products||0} ${Number(d.products||0)===1?'item cadastrado':'itens cadastrados'}`;
    $('#dLowStock').textContent=d.low_stock||0;
    $('#dMonthIn').textContent=money(d.month_in);
    $('#dMonthOut').textContent=money(d.month_out);
    $('#dMonthInHero').textContent=money(d.month_in);
    $('#dMonthOutHero').textContent=money(d.month_out);
    $('#dMonthBalance').textContent=money(d.month_balance);
    $('#dMonthBalance').classList.toggle('negative',Number(d.month_balance||0)<0);
    $('#dSalesCount').textContent=`${d.month_sales||0} ${Number(d.month_sales||0)===1?'venda registrada':'vendas registradas'}`;
    $('#dAvgTicket').textContent=money(d.avg_ticket);
    $('#dMonthSales').textContent=num(d.month_sales||0);
    $('#dMonthEntries').textContent=num(d.month_entries||0);
    $('#dClientsMeta').textContent=`${d.clients||0} ${Number(d.clients||0)===1?'contato':'contatos'}`;
    const tp=d.top_product;
    $('#dTopProduct').textContent=tp?.name||'Sem vendas ainda';
    $('#dTopProductMeta').textContent=tp?`${num(tp.qty)} ${tp.unit} · ${money(tp.total)}`:'Aguardando movimentação';
    const tc=d.top_client;
    $('#dTopClient').textContent=tc?.name||'Sem vendas ainda';
    $('#dTopClientMeta').textContent=tc?`${money(tc.total)} em vendas no mês`:'Aguardando movimentação';
    renderExecutiveChart(d.series||[]);
    $('#recentMovements').innerHTML=d.recent.length?d.recent.map(m=>`
      <div class="activity-item">
        <div class="activity-icon ${m.movement_type==='entrada'?'in':'out'}">${ico(m.movement_type==='entrada'?'i-arrow-down':'i-arrow-up')}</div>
        <div class="activity-main"><b>${esc(m.product_name)}</b><span>${dateBR(m.movement_date)} · ${esc(m.client_name||'Sem cliente')} · ${num(m.quantity)} ${esc(m.unit)}</span></div>
        <div class="activity-value"><strong>${money(m.total_value)}</strong><small>${m.movement_type==='entrada'?'entrada / compra':'saída / venda'}</small></div>
      </div>`).join(''):'<div class="empty premium-empty"><span>'+ico('i-coffee')+'</span><b>Pronto para começar.</b><small>Registre a primeira compra ou venda e o painel executivo ganha vida.</small></div>';
  }catch(e){toast(e.message,true)}
}

async function loadClients(){
  try{
    const q=$('#clientSearch')?.value||'';
    cache.clients=await api('/api/clients?q='+encodeURIComponent(q));
    $('#clientsGrid').innerHTML=cache.clients.length?cache.clients.map(c=>`
      <article class="client-card">
        <div class="client-avatar">${esc(initials(c.name))}</div>
        <h3>${esc(c.name)}</h3>
        <div class="client-meta">
          ${c.phone?`<div class="client-meta-row">${esc(c.phone)}</div>`:''}
          ${c.document?`<div class="client-meta-row">CPF/CNPJ: ${esc(c.document)}</div>`:''}
          ${c.city?`<div class="client-meta-row">${esc(c.city)}</div>`:''}
          ${!c.phone&&!c.document&&!c.city?'Sem dados complementares':''}
        </div>
        <div class="card-actions"><button onclick="showClient(${c.id})">Ver conta</button><button onclick="openClientModal(${c.id})">Editar</button><button onclick="deleteClient(${c.id})">Excluir</button></div>
      </article>`).join(''):'<div class="surface empty">Nenhum cliente encontrado.</div>';
  }catch(e){toast(e.message,true)}
}
$('#clientSearch').addEventListener('input',()=>{clearTimeout(window._cs);window._cs=setTimeout(loadClients,220)});

function openClientModal(id=null){
  const c=id?cache.clients.find(x=>x.id===id):{};
  showModal(`<h2>${id?'Editar cliente':'Novo cliente'}</h2><p class="sub">Dados principais para localizar, vender, comprar e acompanhar saldos.</p><form id="clientForm"><div class="form-grid"><div class="field full"><label>NOME *</label><input name="name" required autocomplete="name" value="${esc(c?.name||'')}" placeholder="Nome completo ou razão social"></div><div class="field"><label>TELEFONE</label><input name="phone" inputmode="tel" value="${esc(c?.phone||'')}" placeholder="(00) 00000-0000"></div><div class="field"><label>CPF / CNPJ</label><input name="document" value="${esc(c?.document||'')}" placeholder="Documento"></div><div class="field full"><label>CIDADE</label><input name="city" value="${esc(c?.city||'')}" placeholder="Cidade / UF"></div><div class="field full"><label>OBSERVAÇÕES</label><textarea name="notes" placeholder="Informações úteis sobre este contato">${esc(c?.notes||'')}</textarea></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Salvar cliente</button></div></form>`);
  $('#clientForm').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));try{await api(id?`/api/clients/${id}`:'/api/clients',{method:id?'PUT':'POST',body:JSON.stringify(data)});closeModal();toast('Cliente salvo.');cache.clients=[];loadClients();loadDashboard()}catch(err){toast(err.message,true)}};
}
async function deleteClient(id){if(!confirm('Excluir este cliente? Os lançamentos antigos ficarão sem vínculo.'))return;try{await api('/api/clients/'+id,{method:'DELETE'});toast('Cliente excluído.');cache.clients=[];loadClients();loadDashboard()}catch(e){toast(e.message,true)}}
async function showClient(id){
  try{
    const d=await api('/api/client-summary/'+id);
    const receive=d.debts.filter(x=>x.balance>0.005&&x.direction==='receber').reduce((a,x)=>a+x.balance,0);
    const pay=d.debts.filter(x=>x.balance>0.005&&x.direction==='pagar').reduce((a,x)=>a+x.balance,0);
    showModal(`<h2>${esc(d.client.name)}</h2><p class="sub">Conta e últimas movimentações deste cadastro.</p><div class="debt-summary"><article class="debt-total receive"><span>A receber</span><strong>${money(receive)}</strong><small>Saldo em aberto</small></article><article class="debt-total pay"><span>A pagar</span><strong>${money(pay)}</strong><small>Saldo em aberto</small></article></div><div class="panel-head"><div><span class="section-kicker">HISTÓRICO</span><h3>Últimas movimentações</h3></div></div><div class="activity-list">${d.movements.slice(0,10).map(m=>`<div class="activity-item"><div class="activity-icon ${m.movement_type==='entrada'?'in':'out'}">${ico(m.movement_type==='entrada'?'i-arrow-down':'i-arrow-up')}</div><div class="activity-main"><b>${esc(m.product_name)}</b><span>${dateBR(m.movement_date)} · ${num(m.quantity)} ${esc(m.unit)}</span></div><div class="activity-value"><strong>${money(m.total_value)}</strong><small>${m.movement_type==='entrada'?'entrada':'saída'}</small></div></div>`).join('')||'<div class="empty">Sem movimentações.</div>'}</div>`);
  }catch(e){toast(e.message,true)}
}

async function loadProducts(){
  try{
    cache.products=await api('/api/products');
    $('#stockRows').innerHTML=cache.products.length?cache.products.map(p=>`<tr><td><b>${esc(p.name)}</b></td><td>${num(p.quantity)}</td><td>${esc(p.unit)}</td><td>${money(p.avg_cost)}</td><td>${money(p.sale_price)}</td><td>${p.min_stock>0&&p.quantity<=p.min_stock?'<span class="pill low">Estoque baixo</span>':'<span class="pill ok">Normal</span>'}</td><td><button class="link-btn" onclick="openProductModal(${p.id})">Editar</button> <button class="link-btn" onclick="deleteProduct(${p.id})">Excluir</button></td></tr>`).join(''):'<tr><td colspan="7" class="empty">Nenhum item cadastrado.</td></tr>';
    $('#stockMobile').innerHTML=cache.products.length?cache.products.map(p=>`
      <article class="mobile-row"><div class="mobile-row-top"><div class="mobile-row-title"><div class="mobile-row-icon neutral">${ico('i-box')}</div><div><h4>${esc(p.name)}</h4><p>${p.min_stock>0&&p.quantity<=p.min_stock?'Estoque baixo':'Estoque normal'}</p></div></div><div class="mobile-row-value">${num(p.quantity)}<div style="font-size:9px;color:#91847b;font-weight:700">${esc(p.unit)}</div></div></div><div class="mobile-row-grid"><div><span>Custo médio</span><strong>${money(p.avg_cost)}</strong></div><div><span>Preço de venda</span><strong>${money(p.sale_price)}</strong></div></div><div class="mobile-row-actions"><button onclick="openProductModal(${p.id})">Editar</button><button onclick="deleteProduct(${p.id})">Excluir</button></div></article>`).join(''):'<div class="empty">Nenhum item cadastrado.</div>';
  }catch(e){toast(e.message,true)}
}
function openProductModal(id=null){
  const p=id?cache.products.find(x=>x.id===id):{};
  showModal(`<h2>${id?'Editar item':'Novo item de estoque'}</h2><p class="sub">Cadastre café, lote ou qualquer item que queira controlar.</p><form id="productForm"><div class="form-grid"><div class="field full"><label>NOME DO PRODUTO *</label><input name="name" required value="${esc(p?.name||'')}" placeholder="Ex.: Café duro tipo 6"></div><div class="field"><label>UNIDADE</label><select name="unit">${['sacas','kg','unidades','lotes'].map(u=>`<option ${p?.unit===u?'selected':''}>${u}</option>`).join('')}</select></div>${id?'':`<div class="field"><label>QUANTIDADE INICIAL</label><input name="quantity" inputmode="decimal" type="number" step="0.01" value="0"></div>`}<div class="field"><label>ESTOQUE MÍNIMO</label><input name="min_stock" inputmode="decimal" type="number" step="0.01" value="${p?.min_stock||0}"></div><div class="field"><label>CUSTO MÉDIO</label><input name="avg_cost" inputmode="decimal" type="number" step="0.01" value="${p?.avg_cost||0}"></div><div class="field"><label>PREÇO DE VENDA</label><input name="sale_price" inputmode="decimal" type="number" step="0.01" value="${p?.sale_price||0}"></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Salvar item</button></div></form>`);
  $('#productForm').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));try{await api(id?`/api/products/${id}`:'/api/products',{method:id?'PUT':'POST',body:JSON.stringify(data)});closeModal();toast('Item salvo.');cache.products=[];loadProducts();loadDashboard()}catch(err){toast(err.message,true)}};
}
async function deleteProduct(id){if(!confirm('Excluir este item do estoque?'))return;try{await api('/api/products/'+id,{method:'DELETE'});toast('Item excluído.');cache.products=[];loadProducts();loadDashboard()}catch(e){toast(e.message,true)}}

async function ensureBase(){if(!cache.clients.length)cache.clients=await api('/api/clients');if(!cache.products.length)cache.products=await api('/api/products')}
async function openMovementModal(type='entrada',id=null){
  try{
    await ensureBase();
    if(!cache.products.length){toast('Cadastre primeiro um item no estoque.',true);goPage('stock');return}
    if(id && !cache.movements.length) cache.movements=await api('/api/movements');
    const m=id?cache.movements.find(x=>x.id===id):null;
    if(id && !m){toast('Movimentação não encontrada.',true);return}
    const today=new Date().toISOString().slice(0,10);
    const selectedType=m?.movement_type||type;
    const selectedCondition=m?.payment_condition||'avista';
    const productOpts=cache.products.map(p=>`<option value="${p.id}" ${m?.product_id===p.id?'selected':''}>${esc(p.name)} · ${num(p.quantity)} ${esc(p.unit)}</option>`).join('');
    const clientOpts='<option value="">Sem cliente / fornecedor</option>'+cache.clients.map(c=>`<option value="${c.id}" ${m?.client_id===c.id?'selected':''}>${esc(c.name)}</option>`).join('');
    showModal(`<h2>${id?'Editar movimentação':'Nova movimentação'}</h2><p class="sub">${id?'Altere os dados e o sistema recalcula estoque e financeiro automaticamente.':'Na compra, o saldo a prazo entra automaticamente em A pagar. Na venda, o saldo vai para A receber.'}</p><form id="movementForm"><div class="form-grid"><div class="field"><label>TIPO</label><select name="movement_type" id="movType"><option value="entrada" ${selectedType==='entrada'?'selected':''}>Entrada / Compra</option><option value="saida" ${selectedType==='saida'?'selected':''}>Saída / Venda</option></select></div><div class="field"><label>DATA</label><input name="movement_date" type="date" value="${m?.movement_date||today}"></div><div class="field full"><label>PRODUTO</label><select name="product_id" id="movProduct">${productOpts}</select></div><div class="field"><label>QUANTIDADE</label><input name="quantity" id="movQty" inputmode="decimal" type="number" step="0.01" min="0.01" required value="${m?.quantity??''}" placeholder="0,00"></div><div class="field"><label>VALOR POR UNIDADE</label><input name="unit_value" id="movUnit" inputmode="decimal" type="number" step="0.01" min="0" value="${m?.unit_value??0}"></div><div class="field full"><label id="movPartyLabel">CLIENTE / FORNECEDOR</label><select name="client_id">${clientOpts}</select></div><div class="field"><label>CONDIÇÃO DE PAGAMENTO</label><select name="payment_condition" id="movCondition"><option value="avista" ${selectedCondition==='avista'?'selected':''}>À vista</option><option value="aprazo" ${selectedCondition==='aprazo'?'selected':''}>A prazo</option></select></div><div class="field" id="movPaidWrap"><label id="movPaidLabel">VALOR PAGO / RECEBIDO AGORA</label><input name="paid_amount" id="movPaid" inputmode="decimal" type="number" step="0.01" min="0" value="${m?.paid_amount??0}"></div><div class="field full" id="movDueWrap"><label>VENCIMENTO DO SALDO</label><input name="due_date" id="movDue" type="date" value="${m?.due_date||''}"></div><div class="field full"><label>OBSERVAÇÃO</label><textarea name="notes" placeholder="Ex.: Café duro, lote 14, retirada no armazém...">${esc(m?.notes||'')}</textarea></div><div class="field full"><div class="movement-finance-summary"><div><span id="movTotalLabel">TOTAL</span><strong id="movTotal">R$ 0,00</strong></div><div><span id="movSettledLabel">PAGO AGORA</span><strong id="movSettled">R$ 0,00</strong></div><div class="balance-box"><span id="movBalanceLabel">SALDO</span><strong id="movBalance">R$ 0,00</strong></div></div><p class="finance-hint" id="movFinanceHint"></p></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">${id?'Salvar alterações':'Salvar movimentação'}</button></div></form>`);

    const calcMov=()=>{
      const total=(parseFloat($('#movQty').value)||0)*(parseFloat($('#movUnit').value)||0);
      if($('#movCondition').value==='avista') $('#movPaid').value=total.toFixed(2);
      const paid=Math.min(Math.max(parseFloat($('#movPaid').value)||0,0),total);
      const balance=Math.max(total-paid,0);
      $('#movTotal').textContent=money(total);
      $('#movSettled').textContent=money(paid);
      $('#movBalance').textContent=money(balance);
    };
    const syncLabels=()=>{
      const isEntry=$('#movType').value==='entrada';
      $('#movPartyLabel').textContent=isEntry?'FORNECEDOR':'CLIENTE';
      $('#movPaidLabel').textContent=isEntry?'VALOR PAGO AO FORNECEDOR AGORA':'VALOR RECEBIDO DO CLIENTE AGORA';
      $('#movTotalLabel').textContent=isEntry?'TOTAL DA COMPRA':'TOTAL DA VENDA';
      $('#movSettledLabel').textContent=isEntry?'PAGO AGORA':'RECEBIDO AGORA';
      $('#movBalanceLabel').textContent=isEntry?'SALDO A PAGAR':'SALDO A RECEBER';
      $('#movFinanceHint').textContent=$('#movCondition').value==='avista'
        ? (isEntry?'Compra à vista: o total fica quitado e não gera saldo para o fornecedor.':'Venda à vista: o total fica quitado e não gera saldo para o cliente.')
        : (isEntry?'Compra a prazo: o valor restante entra automaticamente em Saldo devedor > A pagar.':'Venda a prazo: o valor restante entra automaticamente em Saldo devedor > A receber.');
    };
    const syncCondition=(changed=false)=>{
      const cash=$('#movCondition').value==='avista';
      $('#movPaid').readOnly=cash;
      $('#movDue').disabled=cash;
      $('#movDueWrap').classList.toggle('hidden-field',cash);
      if(cash) $('#movDue').value='';
      else if(changed && !id) $('#movPaid').value='0';
      syncLabels();calcMov();
    };
    const suggest=()=>{
      const p=cache.products.find(x=>x.id===$('#movProduct').value);
      $('#movUnit').value=$('#movType').value==='entrada'?(p?.avg_cost||0):(p?.sale_price||0);
      syncLabels();calcMov();
    };
    $('#movType').onchange=suggest;
    $('#movProduct').onchange=suggest;
    $('#movQty').oninput=calcMov;
    $('#movUnit').oninput=calcMov;
    $('#movPaid').oninput=calcMov;
    let lastCondition=selectedCondition;
    $('#movCondition').onchange=()=>{
      const nextCondition=$('#movCondition').value;
      if(nextCondition==='aprazo' && lastCondition==='avista') $('#movPaid').value='0';
      lastCondition=nextCondition;
      syncCondition(true);
    };
    if(id){syncCondition(false);calcMov()}else{suggest();syncCondition(false)}

    $('#movementForm').onsubmit=async e=>{
      e.preventDefault();
      const data=Object.fromEntries(new FormData(e.target));
      try{
        const result=await api(id?`/api/movements/${id}`:'/api/movements',{method:id?'PUT':'POST',body:JSON.stringify(data)});
        const saleId=id||result.id;
        closeModal();
        toast(id?'Movimentação atualizada.':'Movimentação registrada.');
        cache.products=[];cache.movements=[];cache.debts=[];
        loadDashboard();
        if($('#page-movements').classList.contains('active'))loadMovements();
        if($('#page-stock').classList.contains('active'))loadProducts();
        if($('#page-debts').classList.contains('active'))loadDebts();
        if(!id && data.movement_type==='saida') setTimeout(()=>showModal(`<h2>Venda registrada ✓</h2><p class="sub">A venda foi salva e o estoque já foi atualizado. Quer imprimir o comprovante agora?</p><div class="sale-success"><div><span>Total</span><strong>${money((parseFloat(data.quantity)||0)*(parseFloat(data.unit_value)||0))}</strong></div><div><span>Pagamento</span><strong>${data.payment_condition==='avista'?'À vista':'A prazo'}</strong></div></div><div class="modal-actions"><button class="btn ghost" onclick="closeModal()">Agora não</button><button class="btn primary" onclick="printSale(${saleId})">Imprimir venda</button></div>`),120);
      }catch(err){toast(err.message,true)}
    };
  }catch(e){toast(e.message,true)}
}

async function loadMovements(){try{cache.movements=await api('/api/movements');renderMovements()}catch(e){toast(e.message,true)}}
function printSale(id){
  window.open(`/venda/${id}/imprimir`,'_blank','noopener');
}
function renderMovements(){
  const rows=movementFilter==='all'?cache.movements:cache.movements.filter(m=>m.movement_type===movementFilter);
  $('#movementRows').innerHTML=rows.length?rows.map(m=>`<tr><td>${dateBR(m.movement_date)}</td><td><span class="pill ${m.movement_type==='entrada'?'in':'out'}">${m.movement_type==='entrada'?'Entrada':'Saída'}</span></td><td><b>${esc(m.product_name)}</b></td><td>${esc(m.client_name||'—')}</td><td>${num(m.quantity)} ${esc(m.unit)}</td><td><b>${money(m.total_value)}</b></td><td><span class="payment-badge ${m.payment_condition==='avista'?'cash':'credit'}">${m.payment_condition==='avista'?'À vista':'A prazo'}</span>${m.balance>0.005?`<small class="payment-balance">Saldo ${money(m.balance)}</small>`:''}</td><td><div class="action-group"><button class="link-btn" onclick="openMovementModal('${m.movement_type}',${m.id})">Editar</button>${m.movement_type==='saida'?`<button class="link-btn print" onclick="printSale(${m.id})">Imprimir</button>`:''}</div></td></tr>`).join(''):'<tr><td colspan="8" class="empty">Nenhuma movimentação.</td></tr>';
  $('#movementMobile').innerHTML=rows.length?rows.map(m=>`<article class="mobile-row"><div class="mobile-row-top"><div class="mobile-row-title"><div class="mobile-row-icon ${m.movement_type==='entrada'?'in':'out'}">${ico(m.movement_type==='entrada'?'i-arrow-down':'i-arrow-up')}</div><div><h4>${esc(m.product_name)}</h4><p>${dateBR(m.movement_date)} · ${esc(m.client_name||'Sem cliente')}</p></div></div><div class="mobile-row-value">${money(m.total_value)}</div></div><div class="mobile-row-grid"><div><span>Tipo</span><strong>${m.movement_type==='entrada'?'Entrada / Compra':'Saída / Venda'}</strong></div><div><span>Quantidade</span><strong>${num(m.quantity)} ${esc(m.unit)}</strong></div><div><span>Pagamento</span><strong>${m.payment_condition==='avista'?'À vista':'A prazo'}</strong></div><div><span>${m.movement_type==='entrada'?'A pagar':'A receber'}</span><strong>${money(m.balance||0)}</strong></div></div><div class="mobile-row-actions"><button onclick="openMovementModal('${m.movement_type}',${m.id})">Editar</button>${m.movement_type==='saida'?`<button class="print-mobile" onclick="printSale(${m.id})">Imprimir venda</button>`:''}</div></article>`).join(''):'<div class="empty">Nenhuma movimentação.</div>';
}
$$('.movement-seg button').forEach(b=>b.onclick=()=>{$$('.movement-seg button').forEach(x=>x.classList.remove('active'));b.classList.add('active');movementFilter=b.dataset.filter;renderMovements()});

async function loadDebts(){try{cache.debts=await api('/api/debts');renderDebts()}catch(e){toast(e.message,true)}}
function renderDebts(){
  const open=cache.debts.filter(d=>d.balance>0.005);
  $('#debtReceiveTotal').textContent=money(open.filter(d=>d.direction==='receber').reduce((a,d)=>a+d.balance,0));
  $('#debtPayTotal').textContent=money(open.filter(d=>d.direction==='pagar').reduce((a,d)=>a+d.balance,0));
  const arr=debtFilter==='all'?cache.debts:cache.debts.filter(d=>d.direction===debtFilter);
  $('#debtsList').innerHTML=arr.length?arr.map(d=>`<article class="debt-card"><div><div><span class="pill ${d.direction==='receber'?'in':'out'}">${d.direction==='receber'?'A receber':'A pagar'}</span></div><b style="display:block;margin-top:8px;font-size:13px">${esc(d.client_name||'Sem cliente')}</b><div class="meta">${esc(d.description)}${d.due_date?' · vence '+dateBR(d.due_date):''}</div></div><div><div class="meta">SALDO PENDENTE</div><div class="balance ${d.direction==='receber'?'receive':'pay'}">${money(d.balance)}</div><div class="meta">Original ${money(d.original_amount)} · baixado ${money(d.paid_amount)}</div></div><div class="debt-actions">${d.balance>0.005?`<button class="btn primary" onclick="openPayment(${d.id})">Dar baixa</button>`:'<span class="pill ok">Quitado</span>'}<button class="btn ghost" onclick="deleteDebt(${d.id})">Excluir</button></div></article>`).join(''):'<div class="surface empty">Nenhum saldo encontrado.</div>';
}
$$('.debt-seg button').forEach(b=>b.onclick=()=>{$$('.debt-seg button').forEach(x=>x.classList.remove('active'));b.classList.add('active');debtFilter=b.dataset.direction;renderDebts()});
async function openDebtModal(){
  try{
    if(!cache.clients.length)cache.clients=await api('/api/clients');
    const clients='<option value="">Sem cliente / fornecedor</option>'+cache.clients.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');
    showModal(`<h2>Lançar saldo</h2><p class="sub">Para um valor pendente que não veio de uma movimentação de estoque.</p><form id="debtForm"><div class="form-grid"><div class="field"><label>TIPO</label><select name="direction"><option value="receber">Cliente deve à Rocha</option><option value="pagar">Rocha deve ao cliente / fornecedor</option></select></div><div class="field"><label>VENCIMENTO</label><input type="date" name="due_date"></div><div class="field full"><label>CLIENTE / FORNECEDOR</label><select name="client_id">${clients}</select></div><div class="field full"><label>DESCRIÇÃO</label><input name="description" required placeholder="Ex.: Acerto de café, adiantamento..."></div><div class="field"><label>VALOR TOTAL</label><input inputmode="decimal" type="number" step="0.01" min="0.01" name="original_amount" required></div><div class="field"><label>VALOR JÁ PAGO</label><input inputmode="decimal" type="number" step="0.01" min="0" name="paid_amount" value="0"></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Salvar saldo</button></div></form>`);
    $('#debtForm').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));try{await api('/api/debts',{method:'POST',body:JSON.stringify(data)});closeModal();toast('Saldo lançado.');cache.debts=[];loadDebts();loadDashboard()}catch(err){toast(err.message,true)}};
  }catch(e){toast(e.message,true)}
}
function openPayment(id){
  const d=cache.debts.find(x=>x.id===id),today=new Date().toISOString().slice(0,10);
  showModal(`<h2>Dar baixa</h2><p class="sub">Saldo atual: <b>${money(d.balance)}</b></p><form id="payForm"><div class="form-grid"><div class="field"><label>VALOR DA BAIXA</label><input inputmode="decimal" type="number" step="0.01" min="0.01" max="${d.balance}" name="amount" value="${d.balance}" required></div><div class="field"><label>DATA</label><input type="date" name="payment_date" value="${today}"></div><div class="field full"><label>OBSERVAÇÃO</label><input name="notes" placeholder="Ex.: Pix, dinheiro, transferência..."></div></div><div class="modal-actions"><button type="button" class="btn ghost" onclick="closeModal()">Cancelar</button><button class="btn primary">Confirmar baixa</button></div></form>`);
  $('#payForm').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));try{await api(`/api/debts/${id}/pay`,{method:'POST',body:JSON.stringify(data)});closeModal();toast('Baixa registrada.');cache.debts=[];loadDebts();loadDashboard()}catch(err){toast(err.message,true)}};
}
async function deleteDebt(id){if(!confirm('Excluir este saldo e suas baixas?'))return;try{await api('/api/debts/'+id,{method:'DELETE'});toast('Saldo excluído.');cache.debts=[];loadDebts();loadDashboard()}catch(e){toast(e.message,true)}}

function setupInstall(){
  const btn=$('#installApp');
  const standalone=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const ios=/iphone|ipad|ipod/i.test(navigator.userAgent);
  if(standalone) return;
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstallPrompt=e;btn.classList.remove('hidden')});
  if(ios){
    btn.classList.remove('hidden');
    btn.onclick=()=>showModal(`<h2>Instalar Rocha Café</h2><p class="sub">No iPhone, o aplicativo entra na Tela de Início pelo Safari.</p><div style="background:#f5efe8;border-radius:18px;padding:16px;line-height:1.65;font-size:13px"><b>1.</b> Abra o sistema no Safari.<br><b>2.</b> Toque no botão <b>Compartilhar</b>.<br><b>3.</b> Escolha <b>Adicionar à Tela de Início</b>.<br><b>4.</b> Toque em <b>Adicionar</b>.</div><div class="modal-actions"><button class="btn primary" onclick="closeModal()">Entendi</button></div>`);
  }else{
    btn.onclick=async()=>{if(!deferredInstallPrompt)return;deferredInstallPrompt.prompt();await deferredInstallPrompt.userChoice;deferredInstallPrompt=null;btn.classList.add('hidden')};
  }
}

window.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal()});
if('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(()=>{});
setToday();setupInstall();
const initialPage=new URLSearchParams(location.search).get('page');
if(initialPage&&titles[initialPage]) goPage(initialPage); else {setMobileAction('dashboard');loadDashboard();}
