// RewardTypes.js - Central file for reward types categorization and utilities
import { REWARD_TYPES } from '../../stores/rewardStore';

// Reward categories with their associated reward types
export const REWARD_GROUPS = {
  'Basic Movements': ['move-ego', 'jump', 'rotation', 'crawl'],
  'Poses': ['raisearms', 'headstand', 'liedown', 'sit', 'split'],
  'Combined Actions': ['move-and-raise-arms'],
  'Hand Controls': [
    'left-hand-height', 'left-hand-lateral', 'left-hand-forward',
    'right-hand-height', 'right-hand-lateral', 'right-hand-forward',
    'hand-height', 'hand-lateral'
  ],
  'Foot Controls': [
    'left-foot-height', 'right-foot-height',
    'left-foot-lateral', 'right-foot-lateral',
    'left-foot-forward', 'right-foot-forward'
  ],
  'Other Controls': [
    'stay-upright', 'head-height', 'pelvis-height'
  ],
  'Behavior Rewards': [
    'standing', 'upright', 'movement-control', 'small-control',
    'position', 'balance', 'symmetry', 'energy-efficiency',
    'natural-motion', 'gaze-direction', 'ground-contact',
    'stable-standing', 'natural-walking'
  ]
};

// Initialize parameters for a specific reward type with default values
export function initializeParameters(rewardType) {
  const params = {};
  Object.entries(REWARD_TYPES[rewardType]).forEach(([key, config]) => {
    params[key] = config.default;
  });
  return params;
}

// Get parameters configuration for a reward type
export function getParametersConfig(rewardType) {
  return REWARD_TYPES[rewardType] || {};
}

// Helper function to format parameter labels
export function formatParameterLabel(paramName) {
  return paramName.replace(/_/g, ' ');
}

// Helper function to create initial reward object with default parameters
export function createRewardObject(rewardType, id) {
  return {
    id,
    name: rewardType,
    ...initializeParameters(rewardType)
  };
}

// Combination types for rewards
export const COMBINATION_TYPES = [
  { value: "geometric", label: "Geometric" },
  { value: "additive", label: "Additive" },
  { value: "multiplicative", label: "Multiplicative" },
  { value: "min", label: "Min" },
  { value: "max", label: "Max" }
];