// Formulário de pedido de exclusão de conta (sem login). A API responde sempre igual,
// sem revelar se o e-mail tem conta.
const form = document.getElementById('pedido');
if (form) {
  const msg = form.querySelector('.form-msg');
  const btn = form.querySelector('button');
  const show = (text, ok) => {
    msg.textContent = text;
    msg.className = `form-msg ${ok ? 'ok' : 'err'}`;
    msg.hidden = false;
  };
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    for (const k of Object.keys(data)) if (!String(data[k]).trim()) delete data[k];
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email ?? '')) return show('Informe o e-mail da sua conta.', false);
    btn.disabled = true;
    try {
      const res = await fetch(`${form.dataset.api}/v1/privacy/deletion-requests`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (res.status === 429) return show('Muitos pedidos seguidos. Tente de novo mais tarde.', false);
      if (!res.ok) throw new Error(String(res.status));
      form.reset();
      show('Pedido recebido. Vamos confirmar pelo e-mail informado e concluir a exclusão em até 15 dias.', true);
    } catch {
      show('Não foi possível enviar agora. Tente de novo ou escreva para o e-mail de privacidade.', false);
    } finally {
      btn.disabled = false;
    }
  });
}
