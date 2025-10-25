document.addEventListener('DOMContentLoaded', () => {
  console.log('script loaded');
  const messages = document.getElementById('messages');
  const input = document.getElementById('msg');
  const sendBtn = document.getElementById('sendBtn');
  const imageInput = document.getElementById('imageInput'); // new file input

  function addMessage(who, text) {
    const el = document.createElement('div');
    el.className = 'message ' + who;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    el.appendChild(bubble);
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  async function sendMessage() {
    const msg = input.value.trim();
    const imgFile = imageInput.files[0];

    if (!msg && !imgFile) return;

    addMessage('user', msg || '📷 Image uploaded');
    input.value = '';
    imageInput.value = '';
    sendBtn.disabled = true;

    let payload = {};
    if (msg) payload.message = msg;

    if (imgFile) {
      const reader = new FileReader();
      reader.onload = async () => {
        payload.image = reader.result; // base64 string
        await sendPayload(payload);
      };
      reader.readAsDataURL(imgFile);
    } else {
      await sendPayload(payload);
    }
  }

  async function sendPayload(payload){
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error('Network response not ok');
      const data = await res.json();
      addMessage('bot', data.response || 'No response');
    } catch(err) {
      console.error(err);
      addMessage('bot', 'Error connecting to server');
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  sendBtn && sendBtn.addEventListener('click', sendMessage);
  input && input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
});
