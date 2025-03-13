export default class VideoBuffer {
    constructor() {
      this.mediaRecorder = null;
      this.recordedChunks = [];
      this.canvas = document.createElement('canvas');
      this.ctx = this.canvas.getContext('2d');
      this.stream = null;
    }
  
    async initializeBuffer(width = 320, height = 240) {
      this.canvas.width = width;
      this.canvas.height = height;
      
      this.stream = this.canvas.captureStream(30);
      
      this.mediaRecorder = new MediaRecorder(this.stream, {
        mimeType: 'video/webm;codecs=vp9',
        videoBitsPerSecond: 2500000
      });
  
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.recordedChunks.push(event.data);
        }
      };
    }
  
    updateFrame(imageUrl) {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
      };
      img.onerror = (e) => {
        console.log("Image load error, ignoring:", e);
        // Don't throw an error, just ignore and try again next time
      };
      img.src = imageUrl;
    }
  
    startRecording() {
      this.recordedChunks = [];
      this.mediaRecorder.start();
      
      setTimeout(() => {
        this.mediaRecorder.stop();
      }, 2000);
    }
  
    async getBuffer() {
      return new Promise((resolve) => {
        this.mediaRecorder.onstop = () => {
          const blob = new Blob(this.recordedChunks, {
            type: 'video/webm'
          });
          resolve(blob);
        };
      });
    }
  }