import { RewardConfig } from '../types/rewards';

export function getMoveReward(lowHeight: boolean = false): RewardConfig {
  return {
    rewards: [
      {
        name: 'move-ego',
        move_speed: 2.0,
        stand_height: 1.4,
        move_angle: 0,
        egocentric_target: true,
        low_height: 0.6,
        stay_low: lowHeight
      }
    ],
    weights: [1.0]
  };
} 