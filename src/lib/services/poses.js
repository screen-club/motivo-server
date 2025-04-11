import { websocketService } from './websocket';

export class PoseService {
    static currentAnimation = null;
    static currentPreset = null;
    static currentFps = 4;
    static CONFIG = {
        TARGET_FPS: 30,
        DEFAULT_FPS: 4
    };
    
    // FPS tracking variables
    static frameCounter = 0;
    static lastFrameTimestamp = 0;
    static fpsLoggingInterval = null;

    static getFrameIndices(totalFrames, fps) {
        if (fps <= 0) return [];
        const interval = this.CONFIG.TARGET_FPS / fps;
        return Array.from({ length: totalFrames }, (_, i) => {
            const frameIdx = Math.floor(i * interval);
            return frameIdx < totalFrames ? frameIdx : null;
        }).filter(idx => idx !== null);
    }

    static async loadPoseConfig(preset, animationOptions = {}) {
        console.log('Loading pose config:', preset, 'options:', animationOptions);
        
        // Handle FPS update for running animation
        if (animationOptions.updateParamsOnly && this.currentAnimation && this.currentPreset) {
            if (animationOptions.fps !== this.currentFps) {
                console.log('FPS update requested from', this.currentFps, 'to', animationOptions.fps);
                this.updateAnimationFps(animationOptions.fps);
                return this.currentAnimation;
            }
            return;
        }
        
        if (animationOptions.stopAnimation) {
            console.log('Animation stop requested');
            this.stopCurrentAnimation();
            return;
        }
        
        if (animationOptions.isAnimation) {
            const poseData = preset.data;
            
            // Check if it's a real animation (multiple frames) or a single pose
            const isMultiFrameAnimation = this.isMultiFrameAnimation(preset);
            
            if (isMultiFrameAnimation) {
                // Handle as a true multi-frame animation
                this.currentPreset = preset;
                this.currentFps = animationOptions.fps || this.CONFIG.DEFAULT_FPS;
                console.log('Starting multi-frame animation with FPS:', this.currentFps);
                return this.handleAnimationPlayback(preset, this.currentFps);
            } else {
                // Handle as a single frame "animation"
                console.log('Playing single-frame pose as animation');
                
                // For single pose with pose data
                if (poseData.pose && !Array.isArray(poseData.pose.pose)) {
                    await this.sendSMPLPose(
                        poseData.pose.pose,
                        poseData.pose.trans,
                        poseData.pose.model,
                        poseData.pose.inference_type
                    );
                }
                // For pose animation with just one frame
                else if (poseData.pose?.pose && Array.isArray(poseData.pose.pose)) {
                    await this.sendSMPLPose(
                        poseData.pose.pose[0],
                        poseData.pose.trans?.[0],
                        poseData.pose.model,
                        poseData.pose.inference_type
                    );
                }
                // For qpos
                else if (poseData.pose?.qpos) {
                    const qpos = Array.isArray(poseData.pose.qpos) ? poseData.pose.qpos[0] : poseData.pose.qpos;
                    await this.sendQPosPose(
                        qpos,
                        poseData.pose.inference_type
                    );
                }
            }
        } else {
            // Legacy path - this shouldn't be called anymore with our current changes,
            // but keeping it for backward compatibility
            if (preset.type === 'pose' || preset.data?.pose) {
                const poseData = preset.data;
                
                // For single pose
                if (poseData.pose && !Array.isArray(poseData.pose.pose)) {
                    await this.sendSMPLPose(
                        poseData.pose.pose,
                        poseData.pose.trans,
                        poseData.pose.model,
                        poseData.pose.inference_type
                    );
                }
                // For pose animation
                else if (poseData.pose?.pose && Array.isArray(poseData.pose.pose)) {
                    await this.sendSMPLPose(
                        poseData.pose.pose[0],
                        poseData.pose.trans?.[0],
                        poseData.pose.model,
                        poseData.pose.inference_type
                    );
                }
                // For qpos
                else if (poseData.pose?.qpos) {
                    const qpos = Array.isArray(poseData.pose.qpos) ? poseData.pose.qpos[0] : poseData.pose.qpos;
                    await this.sendQPosPose(
                        qpos,
                        poseData.pose.inference_type
                    );
                }
            }
        }
    }
    
    // Helper method to check if preset contains a multi-frame animation
    static isMultiFrameAnimation(preset) {
        if (!preset.data) return false;
        
        if (Array.isArray(preset.data.pose) && preset.data.pose.length > 1) {
            return true;
        }
        
        if (preset.data.pose?.pose && Array.isArray(preset.data.pose.pose) && preset.data.pose.pose.length > 1) {
            return true;
        }
        
        if (preset.data.pose?.qpos && Array.isArray(preset.data.pose.qpos) && preset.data.pose.qpos.length > 1) {
            return true;
        }
        
        return false;
    }

    static startFpsLogging() {
        // Clear any existing logging interval
        if (this.fpsLoggingInterval) {
            clearInterval(this.fpsLoggingInterval);
        }
        
        // Reset counters
        this.frameCounter = 0;
        this.lastFrameTimestamp = Date.now();
        
        // Create new logging interval (logs every second)
        this.fpsLoggingInterval = setInterval(() => {
            const now = Date.now();
            const elapsed = (now - this.lastFrameTimestamp) / 1000; // Convert to seconds
            const actualFps = this.frameCounter / elapsed;
            
            console.log(`FPS Stats: Target=${this.currentFps}, Actual=${actualFps.toFixed(2)}, Frames sent=${this.frameCounter}`);
            
            // Reset for next period
            this.frameCounter = 0;
            this.lastFrameTimestamp = now;
        }, 1000);
    }

    static stopFpsLogging() {
        if (this.fpsLoggingInterval) {
            clearInterval(this.fpsLoggingInterval);
            this.fpsLoggingInterval = null;
        }
    }

    static updateAnimationFps(newFps) {
        console.log('Updating animation FPS to:', newFps);
        if (!this.currentAnimation || !this.currentPreset) return;
        
        this.currentFps = newFps;
        
        // Stop the current interval but keep track of what we're playing
        clearInterval(this.currentAnimation);
        
        // Restart with new FPS
        const frameDelay = 1000 / newFps;
        console.log('New frame delay:', frameDelay, 'ms');
        
        // Calculate new frame indices
        let frameIndices;
        if (Array.isArray(this.currentPreset.data.pose)) {
            frameIndices = this.getFrameIndices(this.currentPreset.data.pose.length, newFps);
            console.log('Calculated frame indices:', frameIndices.length, 'frames to display');
        } else {
            console.error('Invalid animation data');
            return;
        }
        
        let currentIndex = 0;
        
        const playFrame = async () => {
            const frameIndex = frameIndices[currentIndex];
            const startTime = Date.now();
            
            await this.sendSMPLPose(
                this.currentPreset.data.pose[frameIndex],
                this.currentPreset.data.trans?.[frameIndex],
                this.currentPreset.data.model,
                this.currentPreset.data.inference_type
            );
            
            // Update FPS counter
            this.frameCounter++;
            
            const processingTime = Date.now() - startTime;
            if (processingTime > frameDelay * 0.8) {
                console.warn(`Frame processing time (${processingTime}ms) is close to or exceeds frame delay (${frameDelay}ms)`);
            }
            
            currentIndex = (currentIndex + 1) % frameIndices.length;
        };
        
        // Reset and start FPS logging
        this.startFpsLogging();
        
        // Start the animation interval with new timing
        this.currentAnimation = setInterval(playFrame, frameDelay);
        return this.currentAnimation;
    }

    static async handleAnimationPlayback(preset, fps = this.CONFIG.DEFAULT_FPS, startFrame = 0) {
        console.log('Playing animation:', preset.title, 'FPS:', fps, 'starting from frame:', startFrame);
        
        // Stop any existing animation
        this.stopCurrentAnimation();
        
        const frameDelay = 1000 / fps;
        console.log('Frame delay:', frameDelay, 'ms');
        
        let currentIndex = 0;
        
        // Calculate frame indices for the desired FPS
        let frameIndices;
        
        if (Array.isArray(preset.data.pose)) {
            // This is the classic array format for animations
            frameIndices = this.getFrameIndices(preset.data.pose.length, fps);
            console.log('Total frames in animation:', preset.data.pose.length);
            console.log('Frames to display at current FPS:', frameIndices.length);
            
            // Find the starting index based on startFrame
            currentIndex = frameIndices.findIndex(index => index >= startFrame);
            if (currentIndex === -1) {
                currentIndex = 0; // If not found, start from beginning
            }
        } 
        // Handle the nested array format for animations
        else if (preset.data.pose?.pose && Array.isArray(preset.data.pose.pose) && preset.data.pose.pose.length > 1) {
            frameIndices = this.getFrameIndices(preset.data.pose.pose.length, fps);
            console.log('Total frames in animation (nested format):', preset.data.pose.pose.length);
            console.log('Frames to display at current FPS:', frameIndices.length);
            
            currentIndex = frameIndices.findIndex(index => index >= startFrame);
            if (currentIndex === -1) {
                currentIndex = 0;
            }
        }
        else {
            console.error('Invalid animation data');
            return;
        }
    
        // Reset frame counter and start time for FPS tracking
        this.frameCounter = 0;
        this.lastFrameTimestamp = Date.now();
        
        const playFrame = async () => {
            const frameIndex = frameIndices[currentIndex];
            const startTime = Date.now();
            
            // Handle different animation data formats
            if (Array.isArray(preset.data.pose)) {
                // Standard format
                await this.sendSMPLPose(
                    preset.data.pose[frameIndex],
                    preset.data.trans?.[frameIndex],
                    preset.data.model,
                    preset.data.inference_type
                );
            } else if (preset.data.pose?.pose && Array.isArray(preset.data.pose.pose)) {
                // Nested format
                await this.sendSMPLPose(
                    preset.data.pose.pose[frameIndex],
                    preset.data.pose.trans?.[frameIndex],
                    preset.data.pose.model,
                    preset.data.pose.inference_type
                );
            }
            
            // Update FPS counter
            this.frameCounter++;
            
            const processingTime = Date.now() - startTime;
            if (processingTime > frameDelay * 0.8) {
                console.warn(`Frame processing time (${processingTime}ms) is close to or exceeds frame delay (${frameDelay}ms)`);
            }
            
            currentIndex = (currentIndex + 1) % frameIndices.length;
        };
    
        // Play first frame immediately
        await playFrame();
        
        // Start FPS logging
        this.startFpsLogging();
        
        // Start the animation interval
        this.currentAnimation = setInterval(playFrame, frameDelay);
        return this.currentAnimation;
    }

    static stopCurrentAnimation() {
        this.stopFpsLogging();
        
        if (this.currentAnimation) {
            clearInterval(this.currentAnimation);
            this.currentAnimation = null;
            this.currentPreset = null;
            this.currentFps = this.CONFIG.DEFAULT_FPS;
            console.log('Animation stopped');
        }
    }

    static async sendSMPLPose(pose, trans, model, inferenceType) {
        await websocketService.send({
            type: "load_pose_smpl",
            pose,
            trans,
            model,
            inference_type: inferenceType,
            timestamp: new Date().toISOString()
        });
    }

    static async sendQPosPose(pose, inferenceType) {
        await websocketService.send({
            type: "load_pose",
            pose,
            inference_type: inferenceType,
            timestamp: new Date().toISOString()
        });
    }

    static wsSendPose(frameNb, pose, {
        normalize = false,
        randomRoot = false, 
        countOffset = true,
        useQuat = false,
        eulerOrder = 'XYZ',
        modelType = 'smpl'
    } = {}) {
        const poseToSend = pose.person_1.poses[frameNb];
        const transToSend = pose.person_1.trans[frameNb];
        websocketService.connect();
        
        websocketService.send({
            type: 'load_pose_smpl',
            pose: poseToSend,
            trans: transToSend,
            inference_type: 'goal',
            normalize,
            random_root: randomRoot,
            count_offset: countOffset,
            use_quat: useQuat,
            euler_order: eulerOrder,
            model: modelType
        });
        
        websocketService.disconnect();
    }
}