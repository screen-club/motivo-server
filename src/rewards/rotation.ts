import { RewardConfig } from '../types/rewards';

export function getRotationReward(): RewardConfig {
  return {
    rewards: [
      {
        name: 'rotation',
        axis: 'x',
        target_ang_velocity: 5.0,
        stand_pelvis_height: 0.8
      }
    ],
    weights: [1.0]
  };
} 