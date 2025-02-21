import { websocketService } from './websocketService';

export class PoseService {
    static currentAnimation = null;
    static CONFIG = {
        TARGET_FPS: 30,
        DEFAULT_FPS: 4
    };

    static getFrameIndices(totalFrames, fps) {
        if (fps <= 0) return [];
        const interval = this.CONFIG.TARGET_FPS / fps;
        return Array.from({ length: totalFrames }, (_, i) => {
            const frameIdx = Math.floor(i * interval);
            return frameIdx < totalFrames ? frameIdx : null;
        }).filter(idx => idx !== null);
    }

    static async loadPoseConfig(preset, animationOptions = {}) {
        console.log('Loading pose config:', preset);
        
        if (animationOptions.isAnimation) {
            return this.handleAnimationPlayback(preset, animationOptions.fps);
        }

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

    static async handleAnimationPlayback(preset, fps = this.CONFIG.DEFAULT_FPS) {
        console.log('Playing animation:', preset);
        
        // Stop any existing animation
        this.stopCurrentAnimation();
        
        const frameDelay = 1000 / fps;
        let currentIndex = 0;
        
        // Calculate frame indices for the desired FPS
        let frameIndices;
        if (Array.isArray(preset.data.pose)) {
            frameIndices = this.getFrameIndices(preset.data.pose.length, fps);
        } else {
            console.error('Invalid animation data');
            return;
        }
    
        const playFrame = async () => {
            const frameIndex = frameIndices[currentIndex];
            
            await this.sendSMPLPose(
                preset.data.pose[frameIndex],
                preset.data.trans?.[frameIndex],
                preset.data.model,
                preset.data.inference_type
            );
            currentIndex = (currentIndex + 1) % frameIndices.length;
        };
    
        // Play first frame immediately
        await playFrame();
        
        // Start the animation interval
        this.currentAnimation = setInterval(playFrame, frameDelay);
        return this.currentAnimation;
    }

    static stopCurrentAnimation() {
        if (this.currentAnimation) {
            clearInterval(this.currentAnimation);
            this.currentAnimation = null;
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