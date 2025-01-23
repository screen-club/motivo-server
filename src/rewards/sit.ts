import { RewardConfig } from '../types/rewards';

interface SitOptions {
  pelvisHeightTh?: number;
  constrainedKnees?: boolean;
}

export function getSitReward(options: SitOptions = {}): RewardConfig {
  const {
    pelvisHeightTh = 0,
    constrainedKnees = true
  } = options;

  return {
    rewards: [
      {
        name: 'sit',
        pelvis_height_th: pelvisHeightTh,
        constrained_knees: constrainedKnees
      }
    ],
    weights: [1.0]
  };
} 