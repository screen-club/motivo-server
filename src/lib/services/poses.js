import { websocketService } from './websocketService';

export class PoseService {
    static async loadPoseConfig(preset, animationOptions = {}) {
        console.log('Loading pose config:', preset);
        
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
  static async handleAnimationPlayback(preset, fps = 4) {
    console.log('Playing animation:', preset);
    const frameDelay = 1000 / fps;
    let frameIndex = 0;
    
    const playFrame = async () => {
      if (Array.isArray(preset.data.pose)) {
        await this.sendSMPLPose(
          preset.data.pose[frameIndex],
          preset.data.trans?.[frameIndex],
          preset.data.model,
          preset.data.inference_type
        );
        frameIndex = (frameIndex + 1) % preset.data.pose.length;
      } 
      else if (Array.isArray(preset.data.qpos)) {
        await this.sendQPosPose(
          preset.data.qpos[frameIndex],
          preset.data.inference_type
        );
        frameIndex = (frameIndex + 1) % preset.data.qpos.length;
      }
    };

    // Play first frame immediately
    await playFrame();
    return setInterval(playFrame, frameDelay);
  }

  static async sendSMPLPose(pose, trans, model, inferenceType) {
    console.log('Sending SMPL pose:', { pose, trans, model, inferenceType });
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
    console.log('Sending pose for frame', frameNb, poseToSend);
    
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