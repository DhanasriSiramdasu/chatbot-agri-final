document.addEventListener('DOMContentLoaded', () => {
  console.log('script loaded');

  const messages = document.getElementById('messages');
  const input = document.getElementById('msg');
  const sendBtn = document.getElementById('sendBtn');
  const imageInput = document.getElementById('imageInput');

  // ✅ Utility to add chat messages
  function addMessage(who, text) {
    const el = document.createElement('div');
    el.className = 'message ' + who;

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    // Proper line break conversion
    bubble.innerHTML = text.replace(/\n/g, '<br>');

    el.appendChild(bubble);
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  // ✅ Send text or image payload
  async function sendMessage() {
    const msg = input.value.trim();
    const imgFile = imageInput.files[0];

    if (!msg && !imgFile) return;

    // Show user message
    if (imgFile) {
      addMessage('user', '📸 Analyzing image...');
    } else if (msg) {
      addMessage('user', msg);
    }
    
    input.value = '';
    sendBtn.disabled = true;

    let payload = {};
    if (msg) payload.message = msg;

    if (imgFile) {
      const reader = new FileReader();
      reader.onload = async () => {
        payload.image = reader.result; // base64 string
        await sendPayload(payload);
        imageInput.value = ''; // Reset file input
      };
      reader.onerror = () => {
        // addMessage('bot', '❌ Failed to read image file. Please try a different image.');
        sendBtn.disabled = false;
        imageInput.value = '';
      };
      reader.readAsDataURL(imgFile);
    } else {
      await sendPayload(payload);
    }
  }

  // ✅ Send data to Flask backend and handle response
  async function sendPayload(payload) {
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      // Display response (whether success or error)
      if (data.response) {
        addMessage('bot', data.response);
      } else {
        addMessage('bot', '⚠️ No response received from server.');
      }

    } catch (err) {
      console.error('Network error:', err);
      addMessage('bot', '⚠️ Cannot connect to server. Please check your connection.');
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  // ✅ Button click for sending
  if (sendBtn) {
    sendBtn.addEventListener('click', sendMessage);
  }
  
  // ✅ Enter key for text
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  // ✅ Auto-send when image selected
  if (imageInput) {
    imageInput.addEventListener('change', () => {
      if (imageInput.files.length > 0) {
        sendMessage();
      }
    });
  }
});