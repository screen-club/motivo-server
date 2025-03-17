export default class VideoBuffer {
    constructor() {
      this.mediaRecorder = null;
      this.recordedChunks = [];
      this.canvas = document.createElement('canvas');
      this.ctx = this.canvas.getContext('2d');
      this.stream = null;
      this.videoElement = null;
      this.captureInterval = null;
      this.isCapturing = false;
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
    
    setVideoSource(videoElement) {
      this.videoElement = videoElement;
      return !!videoElement;
    }
    
    captureFrame() {
      if (this.videoElement && this.videoElement.videoWidth > 0) {
        this.ctx.drawImage(
          this.videoElement, 
          0, 0, this.videoElement.videoWidth, this.videoElement.videoHeight,
          0, 0, this.canvas.width, this.canvas.height
        );
        return true;
      }
      return false;
    }
    
    startContinuousCapture() {
      // Clear any existing capture interval
      this.stopContinuousCapture();
      
      // Start capturing frames at 30fps
      this.isCapturing = true;
      this.captureInterval = setInterval(() => {
        if (this.isCapturing) {
          this.captureFrame();
        }
      }, 1000 / 30); // 30fps
    }
    
    stopContinuousCapture() {
      this.isCapturing = false;
      if (this.captureInterval) {
        clearInterval(this.captureInterval);
        this.captureInterval = null;
      }
    }
  
    startRecording(duration = 3000) {
      // Ensure we're capturing frames
      if (!this.isCapturing) {
        this.startContinuousCapture();
      }
      
      this.recordedChunks = [];
      this.mediaRecorder.start();
      
      setTimeout(() => {
        this.mediaRecorder.stop();
      }, duration);
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
    
    cleanup() {
      this.stopContinuousCapture();
      if (this.stream) {
        this.stream.getTracks().forEach(track => track.stop());
      }
    }
  }