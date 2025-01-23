import numpy as np
from humenv import rewards as humenv_rewards
from dm_control.utils import rewards
import mujoco
from typing import Optional
import dataclasses
import re

'''
Model Body Names:
- world
- Pelvis
- L_Hip
- L_Knee
- L_Ankle
- L_Toe
- R_Hip
- R_Knee
- R_Ankle
- R_Toe
- Torso
- Spine
- Chest
- Neck
- Head
- L_Thorax
- L_Shoulder
- L_Elbow
- L_Wrist
- L_Hand
- R_Thorax
- R_Shoulder
- R_Elbow
- R_Wrist
- R_Hand
'''

# Reuse utility functions from humenv rewards
get_xpos = humenv_rewards.get_xpos
get_xmat = humenv_rewards.get_xmat
get_chest_upright = humenv_rewards.get_chest_upright

def list_model_body_names(model: mujoco.MjModel) -> list:
    """List all available body names in the model."""
    return [model.body(i).name for i in range(model.nbody)]

def print_model_info(model: mujoco.MjModel, data: mujoco.MjData):
    """Print debug information about the model."""
    print("\nModel Body Names:")
    body_names = list_model_body_names(model)
    for name in body_names:
        print(f"- {name}")

@dataclasses.dataclass
class StayUprightReward(humenv_rewards.RewardFunction):
    def compute(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
    ) -> float:
        chest_upright = get_chest_upright(model, data)
        return rewards.tolerance(
            chest_upright,
            bounds=(0.9, float("inf")),
            sigmoid="linear",
            margin=1.9,
            value_at_margin=0,
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        if name == "stay-upright":
            return StayUprightReward()
        return None

@dataclasses.dataclass
class HeadHeightReward(humenv_rewards.RewardFunction):
    target_height: float = 1.4

    def compute(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
    ) -> float:
        head_height = get_xpos(model, data, name="Head")[-1]
        return rewards.tolerance(
            head_height,
            bounds=(self.target_height - 0.1, self.target_height + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^head-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            return HeadHeightReward(target_height=target_height)
        return None

@dataclasses.dataclass
class PelvisHeightReward(humenv_rewards.RewardFunction):
    target_height: float = 0.8

    def compute(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
    ) -> float:
        pelvis_height = get_xpos(model, data, name="Pelvis")[-1]
        return rewards.tolerance(
            pelvis_height,
            bounds=(self.target_height - 0.1, self.target_height + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^pelvis-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            return PelvisHeightReward(target_height=target_height)
        return None

@dataclasses.dataclass
class HandHeightReward(humenv_rewards.RewardFunction):
    target_height: float = 1.8

    def compute(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
    ) -> float:
        hand_height = get_xpos(model, data, name="L_Hand")[-1]
        return rewards.tolerance(
            hand_height,
            bounds=(self.target_height - 0.1, self.target_height + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^hand-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            return HandHeightReward(target_height=target_height)
        return None

@dataclasses.dataclass
class HandLateralDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.5

    def compute(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
    ) -> float:
        hand_pos = get_xpos(model, data, name="L_Hand")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        lateral_distance = np.linalg.norm(hand_pos[:2] - pelvis_pos[:2])
        
        return rewards.tolerance(
            lateral_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^hand-lateral-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return HandLateralDistanceReward(target_distance=target_distance)
        return None 

@dataclasses.dataclass
class LeftHandHeightReward(humenv_rewards.RewardFunction):
    target_height: float = 1.0
    stand_height: float = 1.4

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get all necessary positions and states
        hand_height = get_xpos(model, data, name="L_Hand")[-1]
        head_height = get_xpos(model, data, name="Head")[-1]
        chest_upright = get_chest_upright(model, data)
        center_of_mass_velocity = humenv_rewards.get_center_of_mass_linvel(model, data)

        # Calculate standing reward
        standing = rewards.tolerance(
            head_height,
            bounds=(self.stand_height, float("inf")),
            margin=self.stand_height,
            value_at_margin=0.01,
            sigmoid="linear",
        )
        
        # Calculate upright reward
        upright = rewards.tolerance(
            chest_upright,
            bounds=(0.9, float("inf")),
            sigmoid="linear",
            margin=1.9,
            value_at_margin=0,
        )
        
        # Combine standing and upright
        stand_reward = standing * upright
        
        # Calculate movement and control rewards
        dont_move = rewards.tolerance(center_of_mass_velocity, margin=0.5).mean()
        small_control = rewards.tolerance(data.ctrl, margin=1, value_at_margin=0, sigmoid="quadratic").mean()
        small_control = (4 + small_control) / 5

        # Calculate hand height reward
        hand_reward = rewards.tolerance(
            hand_height,
            bounds=(self.target_height - 0.1, self.target_height + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )
        hand_reward = (4 * hand_reward + 1) / 5

        # Combine all rewards
        return small_control * stand_reward * dont_move * hand_reward

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^left-hand-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            return LeftHandHeightReward(target_height=target_height)
        return None

@dataclasses.dataclass
class LeftHandLateralDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.5

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        hand_pos = get_xpos(model, data, name="L_Hand")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        lateral_distance = abs(hand_pos[0] - pelvis_pos[0])  # X-axis for lateral
        return rewards.tolerance(
            lateral_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^left-hand-lateral-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return LeftHandLateralDistanceReward(target_distance=target_distance)
        return None

@dataclasses.dataclass
class LeftHandForwardDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.5

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        hand_pos = get_xpos(model, data, name="L_Hand")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        forward_distance = abs(hand_pos[1] - pelvis_pos[1])  # Y-axis for forward
        return rewards.tolerance(
            forward_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^left-hand-forward-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return LeftHandForwardDistanceReward(target_distance=target_distance)
        return None

# Right Hand rewards follow the same pattern
@dataclasses.dataclass
class RightHandHeightReward(humenv_rewards.RewardFunction):
    target_height: float = 1.0
    stand_height: float = 1.4

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get all necessary positions and states
        hand_height = get_xpos(model, data, name="R_Hand")[-1]
        head_height = get_xpos(model, data, name="Head")[-1]
        chest_upright = get_chest_upright(model, data)
        center_of_mass_velocity = humenv_rewards.get_center_of_mass_linvel(model, data)

        # Calculate standing reward
        standing = rewards.tolerance(
            head_height,
            bounds=(self.stand_height, float("inf")),
            margin=self.stand_height,
            value_at_margin=0.01,
            sigmoid="linear",
        )
        
        # Calculate upright reward
        upright = rewards.tolerance(
            chest_upright,
            bounds=(0.9, float("inf")),
            sigmoid="linear",
            margin=1.9,
            value_at_margin=0,
        )
        
        # Combine standing and upright
        stand_reward = standing * upright
        
        # Calculate movement and control rewards
        dont_move = rewards.tolerance(center_of_mass_velocity, margin=0.5).mean()
        small_control = rewards.tolerance(data.ctrl, margin=1, value_at_margin=0, sigmoid="quadratic").mean()
        small_control = (4 + small_control) / 5

        # Calculate hand height reward
        hand_reward = rewards.tolerance(
            hand_height,
            bounds=(self.target_height - 0.1, self.target_height + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )
        hand_reward = (4 * hand_reward + 1) / 5

        # Combine all rewards
        return small_control * stand_reward * dont_move * hand_reward

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^right-hand-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            return RightHandHeightReward(target_height=target_height)
        return None

@dataclasses.dataclass
class RightHandLateralDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.5

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        hand_pos = get_xpos(model, data, name="R_Hand")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        lateral_distance = abs(hand_pos[0] - pelvis_pos[0])
        return rewards.tolerance(
            lateral_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^right-hand-lateral-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return RightHandLateralDistanceReward(target_distance=target_distance)
        return None

@dataclasses.dataclass
class RightHandForwardDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.5

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        hand_pos = get_xpos(model, data, name="R_Hand")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        forward_distance = abs(hand_pos[1] - pelvis_pos[1])
        return rewards.tolerance(
            forward_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^right-hand-forward-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return RightHandForwardDistanceReward(target_distance=target_distance)
        return None

# Left Foot rewards
@dataclasses.dataclass
class LeftFootHeightReward(humenv_rewards.RewardFunction):
    target_height: float = 0.1

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        foot_height = get_xpos(model, data, name="L_Toe")[-1]
        return rewards.tolerance(
            foot_height,
            bounds=(self.target_height - 0.1, self.target_height + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        if name == "left-foot-height":
            return LeftFootHeightReward()
        pattern = r"^left-foot-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            return LeftFootHeightReward(target_height=target_height)
        return None

@dataclasses.dataclass
class LeftFootLateralDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.2

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        foot_pos = get_xpos(model, data, name="L_Toe")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        lateral_distance = abs(foot_pos[0] - pelvis_pos[0])
        return rewards.tolerance(
            lateral_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        if name == "left-foot-lateral":
            return LeftFootLateralDistanceReward()
        pattern = r"^left-foot-lateral-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return LeftFootLateralDistanceReward(target_distance=target_distance)
        return None

@dataclasses.dataclass
class LeftFootForwardDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.2

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        foot_pos = get_xpos(model, data, name="L_Toe")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        forward_distance = abs(foot_pos[1] - pelvis_pos[1])
        return rewards.tolerance(
            forward_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^left-foot-forward-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return LeftFootForwardDistanceReward(target_distance=target_distance)
        return None

# Right Foot rewards
@dataclasses.dataclass
class RightFootHeightReward(humenv_rewards.RewardFunction):
    target_height: float = 0.1

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        foot_height = get_xpos(model, data, name="R_Toe")[-1]
        return rewards.tolerance(
            foot_height,
            bounds=(self.target_height - 0.1, self.target_height + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^right-foot-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            return RightFootHeightReward(target_height=target_height)
        return None

@dataclasses.dataclass
class RightFootLateralDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.2

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        foot_pos = get_xpos(model, data, name="R_Toe")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        lateral_distance = abs(foot_pos[0] - pelvis_pos[0])
        return rewards.tolerance(
            lateral_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^right-foot-lateral-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return RightFootLateralDistanceReward(target_distance=target_distance)
        return None

@dataclasses.dataclass
class RightFootForwardDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.2

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        foot_pos = get_xpos(model, data, name="R_Toe")
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        forward_distance = abs(foot_pos[1] - pelvis_pos[1])
        return rewards.tolerance(
            forward_distance,
            bounds=(self.target_distance - 0.1, self.target_distance + 0.1),
            margin=0.2,
            value_at_margin=0.01,
            sigmoid="linear",
        )

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^right-foot-forward-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_distance = float(match.group(1))
            return RightFootForwardDistanceReward(target_distance=target_distance)
        return None 