import numpy as np
from humenv import rewards as humenv_rewards
from dm_control.utils import rewards
import mujoco
from typing import Optional
import dataclasses
import re
import inspect
import sys
import humenv

# Define the transformation functions directly here to avoid complex imports
def get_rotation_matrix_from_pelvis(model, data, name="Pelvis"):
    """
    Extract the rotation matrix of the humanoid's pelvis to define its local coordinate system.
    """
    try:
        body_id = model.body(name).id
        rotation_matrix = data.xmat[body_id].reshape(3, 3).copy()
        return rotation_matrix
    except:
        # Fallback to identity matrix if body not found
        return np.eye(3)

def transform_point_to_local_frame(point, origin, rotation_matrix):
    """
    Transform a point from global coordinates to the local coordinate frame
    defined by an origin and rotation matrix.
    """
    # Translate to origin
    translated = point - origin
    
    # Apply inverse rotation (transpose for rotation matrices)
    local_point = rotation_matrix.T @ translated
    
    return local_point

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

def print_available_rewards():
    """Print all available reward types from both humenv.rewards and custom rewards"""
    print("\n=== Standard Rewards from humenv.rewards ===")
    all_rewards = inspect.getmembers(sys.modules["humenv.rewards"], inspect.isclass)
    for reward_class_name, reward_cls in all_rewards:
        if not inspect.isabstract(reward_cls):
            print(f"\n{reward_class_name}:")
            if hasattr(humenv, 'ALL_TASKS'):
                # Print predefined tasks for this reward type if available
                tasks = [task for task in humenv.ALL_TASKS if reward_cls.reward_from_name(task) is not None]
                if tasks:
                    print("  Predefined tasks:")
                    for task in tasks:
                        print(f"    - {task}")
    
    print("\n=== Custom Rewards ===")
    custom_rewards = [
        "stay-upright",
        "head-height (params: target_height)",
        "pelvis-height (params: target_height)",
        "hand-height (params: target_height)",
        "hand-lateral (params: target_distance)",
        "left-hand-height (params: target_height)",
        "left-hand-lateral (params: target_distance)",
        "left-hand-forward (params: target_distance)",
        "right-hand-height (params: target_height)",
        "right-hand-lateral (params: target_distance)",
        "right-hand-forward (params: target_distance)",
        "left-foot-height (params: target_height)",
        "left-foot-lateral (params: target_distance)",
        "left-foot-forward (params: target_distance)",
        "right-foot-height (params: target_height)",
        "right-foot-lateral (params: target_distance)",
        "right-foot-forward (params: target_distance)"
    ]
    
    for reward in custom_rewards:
        print(f"  - {reward}")
    
    print("\n=== Configurable Rewards ===")
    print("  - move-ego (params: move_speed, stand_height, move_angle, egocentric_target, low_height, stay_low)")
    print("  - move-and-raise-arms (params: move_speed, move_angle, left_pose, right_pose, stand_height, low_height, stay_low, egocentric_target, arm_coeff, loc_coeff)")

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
        #print(f"Head height: {head_height}, Target: {self.target_height}")
        return rewards.tolerance(
            head_height,
            bounds=(self.target_height - 0.5, self.target_height + 0.5),
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
    target_height: float = 2.0
    constrained_knees: bool = False
    knees_not_on_ground: bool = False

    def compute(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
    ) -> float:
        # Get all necessary positions and states
        pelvis_height = get_xpos(model, data, name="Pelvis")[-1]
        chest_upright = get_chest_upright(model, data)
        center_of_mass_velocity = humenv_rewards.get_center_of_mass_linvel(model, data)

        # Calculate upright reward (to maintain balance while going down)
        upright = rewards.tolerance(
            chest_upright,
            bounds=(0.9, float("inf")),
            sigmoid="linear",
            margin=1.9,
            value_at_margin=0,
        )
        
        # Calculate movement and control rewards
        dont_move = rewards.tolerance(center_of_mass_velocity, margin=0.5).mean()
        small_control = rewards.tolerance(data.ctrl, margin=1, value_at_margin=0, sigmoid="quadratic").mean()
        small_control = (4 + small_control) / 5

        # Calculate pelvis height reward - the main focus
        pelvis_reward = rewards.tolerance(
            pelvis_height,
            bounds=(0, self.target_height),  # Reward for being at or below target height
            sigmoid="linear",
            margin=0.2,
            value_at_margin=0,
        )

        # Combine all rewards
        return small_control  * dont_move * pelvis_reward

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        pattern = r"^pelvis-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            print(f"Target height fore pelvis: {target_height}")
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
            bounds=(self.target_height - 0.5, self.target_height + 0.5),
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
    right_hand_penalty: bool = True  # Add flag to control right hand penalty

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get all necessary positions and states
        left_hand_height = get_xpos(model, data, name="L_Hand")[-1]
        right_hand_height = get_xpos(model, data, name="R_Hand")[-1]
        head_height = get_xpos(model, data, name="Head")[-1]
        chest_upright = get_chest_upright(model, data)
        center_of_mass_velocity = humenv_rewards.get_center_of_mass_linvel(model, data)

        # Calculate standing reward (reduce weight by making it more lenient)
        standing = rewards.tolerance(
            head_height,
            bounds=(self.stand_height * 0.9, float("inf")),  # Lower minimum standing height
            margin=self.stand_height,
            value_at_margin=0.1,  # More reward at margin
            sigmoid="linear",
        )
        
        # Calculate upright reward (slightly relaxed)
        upright = rewards.tolerance(
            chest_upright,
            bounds=(0.8, float("inf")),  # Lower the upright threshold
            sigmoid="linear",
            margin=1.8,
            value_at_margin=0.1,
        )
        
        # Combine standing and upright with reduced importance
        stand_reward = 0.5 + 0.5 * (standing * upright)  # Allow some reward even without perfect posture
        
        # Calculate movement and control rewards (less strict)
        dont_move = 0.7 + 0.3 * rewards.tolerance(center_of_mass_velocity, margin=0.7).mean()
        small_control = rewards.tolerance(data.ctrl, margin=1, value_at_margin=0.1, sigmoid="quadratic").mean()
        small_control = 0.5 + 0.5 * small_control  # Give some baseline reward

        # Calculate left hand height reward (tighter bounds)
        left_hand_reward = rewards.tolerance(
            left_hand_height,
            bounds=(self.target_height - 0.05, self.target_height + 0.05),  # Tighter bounds
            margin=0.3,
            value_at_margin=0.05,
            sigmoid="gaussian",  # Smoother falloff
        )
        
        # Add a stability bonus for maintaining position over time
        if hasattr(self, 'last_left_hand_height'):
            stability_bonus = rewards.tolerance(
                abs(left_hand_height - self.last_left_hand_height),
                bounds=(0, 0.01),  # Reward stability
                margin=0.1,
                sigmoid="linear",
            )
            left_hand_reward = left_hand_reward * (0.8 + 0.2 * stability_bonus)
        
        # Store current height for next calculation
        self.last_left_hand_height = left_hand_height
        
        # Add right hand penalty (key improvement)
        right_hand_penalty = 1.0
        if self.right_hand_penalty:
            # Penalize right hand for being above a certain height
            right_hand_too_high = rewards.tolerance(
                right_hand_height,
                bounds=(0.6, 0.7),  # Keep right hand below this height 
                margin=0.3,
                value_at_margin=0.1,
                sigmoid="linear",
            )
            right_hand_penalty = right_hand_too_high
        
        # Combine all rewards with stronger emphasis on hand position
        base_reward = small_control * stand_reward * dont_move
        hand_reward = left_hand_reward * right_hand_penalty
        
        # Weight the hand component higher
        final_reward = 0.3 * base_reward + 0.7 * hand_reward
        
        print(f"DEBUG: Left hand: {left_hand_height:.3f}, Right hand: {right_hand_height:.3f}, Target: {self.target_height}, Reward: {final_reward:.3f}")
        
        return final_reward

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        # Handle simple case
        if name == "left-hand-height":
            return LeftHandHeightReward()
            
        # Handle parameterized cases
        pattern = r"^left-hand-height-(\d+\.*\d*)$"
        match = re.search(pattern, name)
        if match:
            target_height = float(match.group(1))
            return LeftHandHeightReward(target_height=target_height)
            
        # Special case for asymmetric configuration
        if name == "left-hand-height-only":
            return LeftHandHeightReward(right_hand_penalty=True)
            
        return None

@dataclasses.dataclass
class LeftHandLateralDistanceReward(humenv_rewards.RewardFunction):
    target_distance: float = 0.5
    debug: bool = False
    use_local_frame: bool = True  # Account for the humanoid's orientation

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get positions for both wrist and hand
        wrist_pos = None
        hand_pos = None
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        
        try:
            wrist_pos = get_xpos(model, data, name="L_Wrist")
        except:
            pass
            
        try:
            hand_pos = get_xpos(model, data, name="L_Hand")
        except:
            pass
        
        # Calculate the hand position using available data
        if wrist_pos is not None and hand_pos is not None:
            # Use midpoint between wrist and hand for better stability
            effective_pos = (wrist_pos + hand_pos) / 2
        elif wrist_pos is not None:
            effective_pos = wrist_pos
        elif hand_pos is not None:
            effective_pos = hand_pos
        else:
            # Fallback if no valid position found
            return 0.0
        
        # Transform to local coordinates if needed
        if self.use_local_frame:
            
            pelvis_rotation = get_rotation_matrix_from_pelvis(model, data)
            local_pos = transform_point_to_local_frame(effective_pos, pelvis_pos, pelvis_rotation)
            
            # In local coordinates, X is lateral (left/right)
            lateral_distance = abs(local_pos[0])
            
            if self.debug:
                print(f"Left hand lateral: global_pos={effective_pos}, local_pos={local_pos}, lateral_distance={lateral_distance:.3f}, target={self.target_distance:.3f}")
        else:
            # Legacy behavior using global coordinates
            lateral_distance = abs(effective_pos[0] - pelvis_pos[0])  # X-axis for lateral
            
            if self.debug:
                wrist_lateral = abs(wrist_pos[0] - pelvis_pos[0]) if wrist_pos is not None else float('nan')
                hand_lateral = abs(hand_pos[0] - pelvis_pos[0]) if hand_pos is not None else float('nan')
                print(f"Left hand lateral: wrist={wrist_lateral:.3f}, hand={hand_lateral:.3f}, combined={lateral_distance:.3f}, target={self.target_distance:.3f}")
            
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
    debug: bool = False
    use_local_frame: bool = True  # Account for the humanoid's orientation

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get positions for both wrist and hand
        wrist_pos = None
        hand_pos = None
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        
        try:
            wrist_pos = get_xpos(model, data, name="L_Wrist")
        except:
            pass
            
        try:
            hand_pos = get_xpos(model, data, name="L_Hand")
        except:
            pass
        
        # Calculate the hand position using available data
        if wrist_pos is not None and hand_pos is not None:
            # Use midpoint between wrist and hand for better stability
            effective_pos = (wrist_pos + hand_pos) / 2
        elif wrist_pos is not None:
            effective_pos = wrist_pos
        elif hand_pos is not None:
            effective_pos = hand_pos
        else:
            # Fallback if no valid position found
            return 0.0
        
        # Transform to local coordinates if needed
        if self.use_local_frame:
            
            pelvis_rotation = get_rotation_matrix_from_pelvis(model, data)
            local_pos = transform_point_to_local_frame(effective_pos, pelvis_pos, pelvis_rotation)
            
            # In local coordinates, Y is forward/backward
            forward_distance = abs(local_pos[1])
            
            if self.debug:
                print(f"Left hand forward: global_pos={effective_pos}, local_pos={local_pos}, forward_distance={forward_distance:.3f}, target={self.target_distance:.3f}")
        else:
            # Legacy behavior using global coordinates
            forward_distance = abs(effective_pos[1] - pelvis_pos[1])  # Y-axis for forward
            
            if self.debug:
                wrist_forward = abs(wrist_pos[1] - pelvis_pos[1]) if wrist_pos is not None else float('nan')
                hand_forward = abs(hand_pos[1] - pelvis_pos[1]) if hand_pos is not None else float('nan')
                print(f"Left hand forward: wrist={wrist_forward:.3f}, hand={hand_forward:.3f}, combined={forward_distance:.3f}, target={self.target_distance:.3f}")
            
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
    debug: bool = False
    use_local_frame: bool = True  # Account for the humanoid's orientation

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get positions for both wrist and hand
        wrist_pos = None
        hand_pos = None
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        
        try:
            wrist_pos = get_xpos(model, data, name="R_Wrist")
        except:
            pass
            
        try:
            hand_pos = get_xpos(model, data, name="R_Hand")
        except:
            pass
        
        # Calculate the hand position using available data
        if wrist_pos is not None and hand_pos is not None:
            # Use midpoint between wrist and hand for better stability
            effective_pos = (wrist_pos + hand_pos) / 2
        elif wrist_pos is not None:
            effective_pos = wrist_pos
        elif hand_pos is not None:
            effective_pos = hand_pos
        else:
            # Fallback if no valid position found
            return 0.0
        
        # Transform to local coordinates if needed
        if self.use_local_frame:
            
            pelvis_rotation = get_rotation_matrix_from_pelvis(model, data)
            local_pos = transform_point_to_local_frame(effective_pos, pelvis_pos, pelvis_rotation)
            
            # In local coordinates, X is lateral (left/right)
            lateral_distance = abs(local_pos[0])
            
            if self.debug:
                print(f"Right hand lateral: global_pos={effective_pos}, local_pos={local_pos}, lateral_distance={lateral_distance:.3f}, target={self.target_distance:.3f}")
        else:
            # Legacy behavior using global coordinates
            lateral_distance = abs(effective_pos[0] - pelvis_pos[0])  # X-axis for lateral
            
            if self.debug:
                wrist_lateral = abs(wrist_pos[0] - pelvis_pos[0]) if wrist_pos is not None else float('nan')
                hand_lateral = abs(hand_pos[0] - pelvis_pos[0]) if hand_pos is not None else float('nan')
                print(f"Right hand lateral: wrist={wrist_lateral:.3f}, hand={hand_lateral:.3f}, combined={lateral_distance:.3f}, target={self.target_distance:.3f}")
            
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
    debug: bool = False
    use_local_frame: bool = True  # Account for the humanoid's orientation

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get positions for both wrist and hand
        wrist_pos = None
        hand_pos = None
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        
        try:
            wrist_pos = get_xpos(model, data, name="R_Wrist")
        except:
            pass
            
        try:
            hand_pos = get_xpos(model, data, name="R_Hand")
        except:
            pass
        
        # Calculate the hand position using available data
        if wrist_pos is not None and hand_pos is not None:
            # Use midpoint between wrist and hand for better stability
            effective_pos = (wrist_pos + hand_pos) / 2
        elif wrist_pos is not None:
            effective_pos = wrist_pos
        elif hand_pos is not None:
            effective_pos = hand_pos
        else:
            # Fallback if no valid position found
            return 0.0
        
        # Transform to local coordinates if needed
        if self.use_local_frame:
            
            pelvis_rotation = get_rotation_matrix_from_pelvis(model, data)
            local_pos = transform_point_to_local_frame(effective_pos, pelvis_pos, pelvis_rotation)
            
            # In local coordinates, Y is forward/backward
            forward_distance = abs(local_pos[1])
            
            if self.debug:
                print(f"Right hand forward: global_pos={effective_pos}, local_pos={local_pos}, forward_distance={forward_distance:.3f}, target={self.target_distance:.3f}")
        else:
            # Legacy behavior using global coordinates
            forward_distance = abs(effective_pos[1] - pelvis_pos[1])  # Y-axis for forward
            
            if self.debug:
                wrist_forward = abs(wrist_pos[1] - pelvis_pos[1]) if wrist_pos is not None else float('nan')
                hand_forward = abs(hand_pos[1] - pelvis_pos[1]) if hand_pos is not None else float('nan')
                print(f"Right hand forward: wrist={wrist_forward:.3f}, hand={hand_forward:.3f}, combined={forward_distance:.3f}, target={self.target_distance:.3f}")
            
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
        # Add logging to track foot height and target
        print(f"Left foot height: {foot_height:.3f}, Target: {self.target_height:.3f}")
        
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
    debug: bool = False
    use_local_frame: bool = True  # Account for the humanoid's orientation

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get positions for both ankle and toe
        ankle_pos = None
        toe_pos = None
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        
        try:
            ankle_pos = get_xpos(model, data, name="L_Ankle")
        except:
            pass
            
        try:
            toe_pos = get_xpos(model, data, name="L_Toe")
        except:
            pass
        
        # Calculate the foot position using available data
        if ankle_pos is not None and toe_pos is not None:
            # Use midpoint between ankle and toe for better stability
            foot_pos = (ankle_pos + toe_pos) / 2
        elif ankle_pos is not None:
            foot_pos = ankle_pos
        elif toe_pos is not None:
            foot_pos = toe_pos
        else:
            # Fallback if no valid position found
            return 0.0
        
        # Transform to local coordinates if needed
        if self.use_local_frame:
            
            pelvis_rotation = get_rotation_matrix_from_pelvis(model, data)
            local_pos = transform_point_to_local_frame(foot_pos, pelvis_pos, pelvis_rotation)
            
            # In local coordinates, X is lateral (left/right)
            lateral_distance = abs(local_pos[0])
            
            if self.debug:
                print(f"Left foot lateral: global_pos={foot_pos}, local_pos={local_pos}, lateral_distance={lateral_distance:.3f}, target={self.target_distance:.3f}")
        else:
            # Legacy behavior using global coordinates
            lateral_distance = abs(foot_pos[0] - pelvis_pos[0])
            
            if self.debug:
                ankle_lateral = abs(ankle_pos[0] - pelvis_pos[0]) if ankle_pos is not None else float('nan')
                toe_lateral = abs(toe_pos[0] - pelvis_pos[0]) if toe_pos is not None else float('nan')
                print(f"Left foot lateral: ankle={ankle_lateral:.3f}, toe={toe_lateral:.3f}, combined={lateral_distance:.3f}, target={self.target_distance:.3f}")
            
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
    debug: bool = False
    use_local_frame: bool = True  # Account for the humanoid's orientation

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get positions for both ankle and toe
        ankle_pos = None
        toe_pos = None
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        
        try:
            ankle_pos = get_xpos(model, data, name="L_Ankle")
        except:
            pass
            
        try:
            toe_pos = get_xpos(model, data, name="L_Toe")
        except:
            pass
        
        # Calculate the foot position using available data
        if ankle_pos is not None and toe_pos is not None:
            # Use midpoint between ankle and toe for better stability
            foot_pos = (ankle_pos + toe_pos) / 2
        elif ankle_pos is not None:
            foot_pos = ankle_pos
        elif toe_pos is not None:
            foot_pos = toe_pos
        else:
            # Fallback if no valid position found
            return 0.0
        
        # Transform to local coordinates if needed
        if self.use_local_frame:
            
            pelvis_rotation = get_rotation_matrix_from_pelvis(model, data)
            local_pos = transform_point_to_local_frame(foot_pos, pelvis_pos, pelvis_rotation)
            
            # In local coordinates, Y is forward/backward
            forward_distance = abs(local_pos[1])
            
            if self.debug:
                print(f"Left foot forward: global_pos={foot_pos}, local_pos={local_pos}, forward_distance={forward_distance:.3f}, target={self.target_distance:.3f}")
        else:
            # Legacy behavior using global coordinates
            forward_distance = abs(foot_pos[1] - pelvis_pos[1])  # Y-axis for forward
            
            if self.debug:
                ankle_forward = abs(ankle_pos[1] - pelvis_pos[1]) if ankle_pos is not None else float('nan')
                toe_forward = abs(toe_pos[1] - pelvis_pos[1]) if toe_pos is not None else float('nan')
                print(f"Left foot forward: ankle={ankle_forward:.3f}, toe={toe_forward:.3f}, combined={forward_distance:.3f}, target={self.target_distance:.3f}")
            
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
    debug: bool = False
    use_local_frame: bool = True  # Account for the humanoid's orientation

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get positions for both ankle and toe
        ankle_pos = None
        toe_pos = None
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        
        try:
            ankle_pos = get_xpos(model, data, name="R_Ankle")
        except:
            pass
            
        try:
            toe_pos = get_xpos(model, data, name="R_Toe")
        except:
            pass
        
        # Calculate the foot position using available data
        if ankle_pos is not None and toe_pos is not None:
            # Use midpoint between ankle and toe for better stability
            foot_pos = (ankle_pos + toe_pos) / 2
        elif ankle_pos is not None:
            foot_pos = ankle_pos
        elif toe_pos is not None:
            foot_pos = toe_pos
        else:
            # Fallback if no valid position found
            return 0.0
        
        # Transform to local coordinates if needed
        if self.use_local_frame:
            
            pelvis_rotation = get_rotation_matrix_from_pelvis(model, data)
            local_pos = transform_point_to_local_frame(foot_pos, pelvis_pos, pelvis_rotation)
            
            # In local coordinates, X is lateral (left/right)
            lateral_distance = abs(local_pos[0])
            
            if self.debug:
                print(f"Right foot lateral: global_pos={foot_pos}, local_pos={local_pos}, lateral_distance={lateral_distance:.3f}, target={self.target_distance:.3f}")
        else:
            # Legacy behavior using global coordinates
            lateral_distance = abs(foot_pos[0] - pelvis_pos[0])
            
            if self.debug:
                ankle_lateral = abs(ankle_pos[0] - pelvis_pos[0]) if ankle_pos is not None else float('nan')
                toe_lateral = abs(toe_pos[0] - pelvis_pos[0]) if toe_pos is not None else float('nan')
                print(f"Right foot lateral: ankle={ankle_lateral:.3f}, toe={toe_lateral:.3f}, combined={lateral_distance:.3f}, target={self.target_distance:.3f}")
            
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
    debug: bool = False
    use_local_frame: bool = True  # Account for the humanoid's orientation

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get positions for both ankle and toe
        ankle_pos = None
        toe_pos = None
        pelvis_pos = get_xpos(model, data, name="Pelvis")
        
        try:
            ankle_pos = get_xpos(model, data, name="R_Ankle")
        except:
            pass
            
        try:
            toe_pos = get_xpos(model, data, name="R_Toe")
        except:
            pass
        
        # Calculate the foot position using available data
        if ankle_pos is not None and toe_pos is not None:
            # Use midpoint between ankle and toe for better stability
            foot_pos = (ankle_pos + toe_pos) / 2
        elif ankle_pos is not None:
            foot_pos = ankle_pos
        elif toe_pos is not None:
            foot_pos = toe_pos
        else:
            # Fallback if no valid position found
            return 0.0
        
        # Transform to local coordinates if needed
        if self.use_local_frame:
            
            pelvis_rotation = get_rotation_matrix_from_pelvis(model, data)
            local_pos = transform_point_to_local_frame(foot_pos, pelvis_pos, pelvis_rotation)
            
            # In local coordinates, Y is forward/backward
            forward_distance = abs(local_pos[1])
            
            if self.debug:
                print(f"Right foot forward: global_pos={foot_pos}, local_pos={local_pos}, forward_distance={forward_distance:.3f}, target={self.target_distance:.3f}")
        else:
            # Legacy behavior using global coordinates
            forward_distance = abs(foot_pos[1] - pelvis_pos[1])  # Y-axis for forward
            
            if self.debug:
                ankle_forward = abs(ankle_pos[1] - pelvis_pos[1]) if ankle_pos is not None else float('nan')
                toe_forward = abs(toe_pos[1] - pelvis_pos[1]) if toe_pos is not None else float('nan')
                print(f"Right foot forward: ankle={ankle_forward:.3f}, toe={toe_forward:.3f}, combined={forward_distance:.3f}, target={self.target_distance:.3f}")
            
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