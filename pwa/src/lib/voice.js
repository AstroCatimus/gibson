/**
 * Gibson — Voice input for ambient mode.
 * Browser Speech Recognition API. Client-side transcription.
 * Tap → start. Silence or second tap → send transcript to Gibson.
 */

window.Gibson = window.Gibson || {};

Gibson.voice = {
  recognition: null,
  isRecording: false,
  transcript: '',

  init() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = false;
    this.recognition.interimResults = true;
    this.recognition.lang = 'en-US';

    this.recognition.onresult = (event) => {
      this.transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        this.transcript += event.results[i][0].transcript;
      }
    };

    this.recognition.onend = () => {
      this.isRecording = false;
      this._updateButton();
      if (this.transcript.trim()) {
        this._sendToGibson(this.transcript.trim());
      }
    };

    // Wire up mic button
    const btn = document.getElementById('mic-btn');
    if (btn) {
      btn.addEventListener('click', () => this.toggle());
    }
  },

  toggle() {
    if (this.isRecording) {
      this.recognition.stop();
    } else {
      this.transcript = '';
      this.isRecording = true;
      this._updateButton();
      this.recognition.start();
    }
  },

  _updateButton() {
    const btn = document.getElementById('mic-btn');
    if (btn) btn.classList.toggle('recording', this.isRecording);
  },

  async _sendToGibson(text) {
    try {
      const result = await Gibson.api.sendMessage(text, 'ambient');
      this._showResponse(result.response);
    } catch (e) {
      this._showResponse('Sorry, I couldn\'t process that right now.');
    }
  },

  _showResponse(text) {
    // Show a brief overlay with Gibson's response
    const overlay = document.createElement('div');
    overlay.style.cssText = `
      position: fixed; top: 60px; left: 16px; right: 16px; z-index: 300;
      background: var(--bg-card); border: 1px solid var(--accent);
      border-radius: 8px; padding: 16px; color: var(--text-primary);
      font-size: 14px; line-height: 1.5; animation: fadeIn 0.2s;
    `;
    overlay.textContent = text;
    document.body.appendChild(overlay);

    // Auto-dismiss after 8 seconds or on tap
    const dismiss = () => overlay.remove();
    overlay.addEventListener('click', dismiss);
    setTimeout(dismiss, 8000);
  },
};
