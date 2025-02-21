import { websocketService } from './websocketService';

export class PoseService {
    static currentAnimation = null;
    static CONFIG = {
        TARGET_FPS: 30, // Original animation FPS
        DEFAULT_FPS: 4  // Default playback FPS
    };

    static getFrameIndices(totalFrames, fps) {
        if (fps <= 0) return [];
        
        // Calculate frame interval to achieve desired FPS
        const interval = this.CONFIG.TARGET_FPS / fps;
        
        // Generate frame indices
        return Array.from({ length: totalFrames }, (_, i) => {
            const frameIdx = Math.floor(i * interval);
            return frameIdx < totalFrames ? frameIdx : null;
        }).filter(idx => idx !== null);
    }

    static async loadPoseConfig(preset, animationOptions = {}) {
        // Handle animation playback request
        if (animationOptions.isAnimation) {
            return this.handleAnimationPlayback(preset, animationOptions.fps, animationOptions.speedFactor);
        }
        
        // Handle single pose loading
        if (preset.type === 'pose' || preset.data?.pose) {
            const poseData = preset.data;
            
            // For single pose
            if (poseData.pose && !Array.isArray(poseData.pose)) {
                await this.sendSMPLPose(
                    poseData.pose,
                    poseData.trans,
                    poseData.model,
                    poseData.inference_type
                );
            }
            // For first frame of animation
            else if (Array.isArray(poseData.pose)) {
                await this.sendSMPLPose(
                    poseData.pose[0],
                    poseData.trans?.[0],
                    poseData.model,
                    poseData.inference_type
                );
            }
            // For qpos
            else if (poseData.qpos) {
                const qpos = Array.isArray(poseData.qpos) ? poseData.qpos[0] : poseData.qpos;
                await this.sendQPosPose(
                    qpos,
                    poseData.inference_type
                );
            }
        }
    }

    static async handleAnimationPlayback(preset, fps = this.CONFIG.DEFAULT_FPS, speedFactor = 1) {
        console.log('Starting animation playback:', preset, 'FPS:', fps, 'Speed:', speedFactor);
        
        // Stop any existing animation
        this.stopCurrentAnimation();
        
        const frameDelay = 1000 / fps;
        let currentIndex = 0;
        
        // Calculate frame indices for the desired FPS
        let frameIndices;
        if (Array.isArray(preset.data.pose)) {
            frameIndices = this.getFrameIndices(preset.data.pose.length, fps);
        } else if (Array.isArray(preset.data.qpos)) {
            frameIndices = this.getFrameIndices(preset.data.qpos.length, fps);
        } else {
            console.error('Invalid animation data');
            return;
        }

        console.log(`Reduced frames from ${preset.data.pose?.length || preset.data.qpos?.length} to ${frameIndices.length} at ${fps} FPS`);
        
        const playFrame = async () => {
            try {
                const frameIndex = frameIndices[currentIndex];
                
                // Handle SMPL pose animation
                if (Array.isArray(preset.data.pose)) {
                    await this.sendSMPLPose(
                        preset.data.pose[frameIndex],
                        preset.data.trans?.[frameIndex],
                        preset.data.model,
                        preset.data.inference_type
                    );
                }
                // Handle qpos animation
                else if (Array.isArray(preset.data.qpos)) {
                    await this.sendQPosPose(
                        preset.data.qpos[frameIndex],
                        preset.data.inference_type
                    );
                }

                // Update index with speed factor
                currentIndex = (currentIndex + Math.max(1, Math.round(speedFactor))) % frameIndices.length;
                
            } catch (error) {
                console.error('Error playing animation frame:', error);
                this.stopCurrentAnimation();
            }
        };

        // Play first frame immediately
        await playFrame();
        
        // Start the animation interval
        this.currentAnimation = setInterval(playFrame, frameDelay);
        return this.currentAnimation;
    }

    static async sendSMPLPose(pose, trans, model, inferenceType) {
        console.log('Sending SMPL pose:', { pose, trans, model, inferenceType });
        await websocketService.send({
            type: "load_pose_smpl",
            pose,
            trans,
            model,
            inference_type: inferenceType || 'goal',
            timestamp: new Date().toISOString()
        });
    }

    static async sendQPosPose(pose, inferenceType) {
        await websocketService.send({
            type: "load_pose",
            pose,
            inference_type: inferenceType || 'goal',
            timestamp: new Date().toISOString()
        });
    }

    static stopCurrentAnimation() {
        if (this.currentAnimation) {
            clearInterval(this.currentAnimation);
            this.currentAnimation = null;
        }
    }
}