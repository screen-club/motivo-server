import json
import asyncio
import websockets
from typing import Dict, Any, List, Optional
import traceback
import os
import argparse
import sys

# import from env BACKEND_DOMAIN
BACKEND_DOMAIN = os.getenv("VITE_BACKEND_DOMAIN", "localhost")
WS_PORT = os.getenv("VITE_WS_PORT", 8765)
API_PORT = os.getenv("VITE_API_PORT", 5000)

async def test_individual_reward(websocket, reward_config: Dict[Any, Any], name: str, settings: Dict[Any, Any] = None, add_to_existing: bool = False):
    """Test a single reward configuration"""
    try:
        print(f"\n=== Testing {name} ===")
        
        # Request model info
        debug_message = {
            "type": "debug_model_info",
            "timestamp": "test"
        }
        await websocket.send(json.dumps(debug_message))
        debug_response = await websocket.recv()
        print("\nModel Body Names:", end=" ")
        try:
            response_data = json.loads(debug_response)
            if isinstance(response_data, list):
                print(", ".join(response_data))
            else:
                print(f"Error: {debug_response}")
        except json.JSONDecodeError:
            print(f"Invalid JSON: {debug_response}")
        
        # Print reward info in a single line for each reward
        for reward in reward_config["rewards"]:
            reward_type = reward["name"]
            debug_enabled = reward.get("debug", False)
            
            # Handle different reward parameter patterns
            if reward_type == "position" and "targets" in reward:
                target_str = ", ".join([f"{body}: ({t.get('x', 'None')}, {t.get('y', 'None')}, {t.get('z', 'None')})" 
                                       for body, t in reward["targets"].items()])
                print(f"Reward: {reward_type} - Targets: {target_str} - Debug: {debug_enabled}")
            elif "target_height" in reward:
                print(f"Reward: {reward_type} - Target Height: {reward['target_height']}m - Debug: {debug_enabled}")
            elif "target_distance" in reward:
                print(f"Reward: {reward_type} - Target Distance: {reward['target_distance']}m - Debug: {debug_enabled}")
            else:
                print(f"Reward: {reward_type} - Debug: {debug_enabled}")

        combination_type = reward_config.get('combinationType', reward_config.get('combination_type', 'multiplicative'))
        print(f"Config: {combination_type} combination, Weights: {reward_config.get('weights', [1.0])}")
        
        message = {
            "type": "request_reward",
            "reward": reward_config,
            "timestamp": "test",
            "add_to_existing": add_to_existing
        }
        
        await websocket.send(json.dumps(message))
        response = await websocket.recv()
        print(f"Response: {response}")
        
        # Wait a bit for visualization
        wait_time = settings.get("wait_time", 10) if settings else 10
        print(f"Waiting {wait_time} seconds for visualization...")
        await asyncio.sleep(wait_time)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        print(traceback.format_exc())
        raise

async def run_basic_tests(websocket, settings):
    """Run basic tests for individual rewards"""
    print("\n===== RUNNING BASIC REWARD TESTS =====")
    
    # Test standing and upright rewards
    await test_individual_reward(
        websocket,
        {
            "rewards": [{"name": "stay-upright", "debug": True}],
            "weights": [1.0],
            "combinationType": "multiplicative"
        },
        "StayUprightReward Test",
        settings
    )
    
    await test_individual_reward(
        websocket,
        {
            "rewards": [{"name": "stable-standing", "debug": True}],
            "weights": [1.0],
            "combinationType": "multiplicative"
        },
        "StableStandingReward Test",
        settings
    )

async def run_height_tests(websocket, settings):
    """Run tests for height rewards"""
    print("\n===== RUNNING HEIGHT REWARD TESTS =====")
    
    # Test height rewards for different body parts
    height_tests = [
        ("head-height", 1.5),
        ("pelvis-height", 0.8),
        ("left-hand-height", 1.5),
        ("right-hand-height", 1.5),
    ]

    for reward_name, height in height_tests:
        await test_individual_reward(
            websocket,
            {
                "rewards": [
                    {"name": reward_name, "target_height": height, "debug": True}
                ],
                "weights": [1.0],
                "combinationType": "multiplicative"
            },
            f"{reward_name} Test (height: {height}m)",
            settings
        )

async def run_distance_tests(websocket, settings):
    """Run tests for distance rewards (lateral and forward)"""
    print("\n===== RUNNING DISTANCE REWARD TESTS =====")
    
    # Test distance rewards for hands and feet
    distance_tests = [
        ("left-hand-lateral", 0.5),
        ("left-hand-forward", 0.5),
        ("right-hand-lateral", 0.5),
        ("right-hand-forward", 0.5),
        ("left-foot-lateral", 0.3),
        ("left-foot-forward", 0.3),
        ("right-foot-lateral", 0.3),
        ("right-foot-forward", 0.3)
    ]

    for reward_name, distance in distance_tests:
        await test_individual_reward(
            websocket,
            {
                "rewards": [
                    {"name": reward_name, "target_distance": distance, "debug": True}
                ],
                "weights": [1.0],
                "combinationType": "multiplicative"
            },
            f"{reward_name} Test (distance: {distance}m)",
            settings
        )

async def run_position_reward_tests(websocket, settings):
    """Run tests for the improved PositionReward system"""
    print("\n===== RUNNING POSITION REWARD TESTS =====")
    
    # Test position rewards with various configurations
    
    # Simple test with one target
    await test_individual_reward(
        websocket,
        {
            "rewards": [
                {
                    "name": "position",
                    "debug": True,
                    "targets": {
                        "L_Hand": {
                            "x": 0.5,
                            "y": 0.3,
                            "z": 1.2,
                            "weight": 1.0
                        }
                    }
                }
            ],
            "weights": [1.0],
            "combinationType": "multiplicative"
        },
        "PositionReward Test (single target)",
        settings
    )
    
    # Multiple targets with relative positioning
    await test_individual_reward(
        websocket,
        {
            "rewards": [
                {
                    "name": "position",
                    "debug": True,
                    "targets": {
                        "L_Hand": {
                            "x": 0.5,
                            "y": 0.3,
                            "z": 1.2,
                            "relative_to": "Pelvis",
                            "alternatives": ["LeftHand", "left_hand"],
                            "weight": 1.0
                        },
                        "R_Hand": {
                            "x": -0.5,
                            "y": 0.3,
                            "z": 1.2,
                            "relative_to": "Pelvis",
                            "alternatives": ["RightHand", "right_hand"],
                            "weight": 1.0
                        }
                    },
                    "upright_weight": 0.3,
                    "control_weight": 0.2
                }
            ],
            "weights": [1.0],
            "combinationType": "multiplicative"
        },
        "PositionReward Test (multiple targets with relative positioning)",
        settings
    )
    
    # Partial targeting (only x and z coordinates)
    await test_individual_reward(
        websocket,
        {
            "rewards": [
                {
                    "name": "position",
                    "debug": True,
                    "targets": {
                        "Head": {
                            "x": 0.0,
                            "z": 1.7,
                            "weight": 1.0
                        }
                    }
                }
            ],
            "weights": [1.0],
            "combinationType": "multiplicative"
        },
        "PositionReward Test (partial axis targeting)",
        settings
    )

async def run_behavior_reward_tests(websocket, settings):
    """Run tests for behavior rewards"""
    print("\n===== RUNNING BEHAVIOR REWARD TESTS =====")
    
    behavior_tests = [
        {
            "rewards": [{"name": "balance", "debug": True}],
            "weights": [1.0],
            "name": "BalanceReward Test"
        },
        {
            "rewards": [{"name": "symmetry", "debug": True}],
            "weights": [1.0],
            "name": "SymmetryReward Test"
        },
        {
            "rewards": [{"name": "ground-contact", "debug": True}],
            "weights": [1.0],
            "name": "GroundContactReward Test"
        },
        {
            "rewards": [{"name": "stable-standing", "debug": True}],
            "weights": [1.0],
            "name": "StableStandingReward Test"
        },
        {
            "rewards": [{"name": "natural-walking", "debug": True}],
            "weights": [1.0],
            "name": "NaturalWalkingReward Test"
        }
    ]
    
    for test in behavior_tests:
        await test_individual_reward(
            websocket,
            {
                "rewards": test["rewards"],
                "weights": test["weights"],
                "combinationType": "multiplicative"
            },
            test["name"],
            settings
        )

async def run_combined_reward_tests(websocket, settings):
    """Run tests for combined rewards"""
    print("\n===== RUNNING COMBINED REWARD TESTS =====")
    
    # Test accumulating rewards (add_to_existing)
    await test_individual_reward(
        websocket,
        {
            "rewards": [
                {"name": "stay-upright", "debug": True}
            ],
            "weights": [1.0],
            "combinationType": "multiplicative"
        },
        "Base Upright Reward",
        settings
    )
    
    # Add a second reward to the existing one
    await test_individual_reward(
        websocket,
        {
            "rewards": [
                {"name": "right-hand-height", "target_height": 1.5, "debug": True}
            ],
            "weights": [1.0],
            "combinationType": "multiplicative"
        },
        "Adding Right Hand Height to Existing Reward",
        settings,
        add_to_existing=True
    )
    
    # Add a third reward
    await test_individual_reward(
        websocket,
        {
            "rewards": [
                {"name": "left-foot-lateral", "target_distance": 0.4, "debug": True}
            ],
            "weights": [1.0],
            "combinationType": "multiplicative"
        },
        "Adding Left Foot Lateral to Existing Rewards",
        settings,
        add_to_existing=True
    )
    
    # Clean up to prepare for next tests
    await clean_rewards(websocket)
    
    # Test more complex combinations
    combined_tests = [
        {
            "rewards": [
                {"name": "stable-standing", "debug": True},
                {"name": "left-hand-lateral", "target_distance": 0.7, "debug": True},
                {"name": "right-hand-lateral", "target_distance": 0.7, "debug": True}
            ],
            "weights": [1.0, 0.8, 0.8],
            "name": "Hands Out to Sides"
        },
        {
            "rewards": [
                {"name": "stable-standing", "debug": True},
                {"name": "left-hand-forward", "target_distance": 0.5, "debug": True},
                {"name": "right-hand-forward", "target_distance": 0.5, "debug": True}
            ],
            "weights": [1.0, 0.8, 0.8],
            "name": "Hands Forward"
        },
        {
            "rewards": [
                {"name": "balance", "debug": True},
                {"name": "symmetry", "debug": True},
                {
                    "name": "position",
                    "debug": True,
                    "targets": {
                        "L_Hand": {"x": 0.5, "z": 1.6, "weight": 1.0},
                        "R_Hand": {"x": -0.5, "z": 1.6, "weight": 1.0}
                    }
                }
            ],
            "weights": [1.0, 1.0, 1.5],
            "name": "Balanced Pose with Hands Up"
        }
    ]
    
    for test in combined_tests:
        await test_individual_reward(
            websocket,
            {
                "rewards": test["rewards"],
                "weights": test["weights"],
                "combinationType": "multiplicative"
            },
            test["name"],
            settings
        )

async def clean_rewards(websocket):
    """Clean up rewards"""
    print("\nCleaning up rewards...")
    cleanup_message = {
        "type": "clean_rewards",
        "timestamp": "test"
    }
    await websocket.send(json.dumps(cleanup_message))
    cleanup_response = await websocket.recv()
    print(f"Cleanup response: {cleanup_response}")

async def run_reward_tests(test_categories: List[str] = None, settings: Dict[str, Any] = None):
    """Run a series of reward tests based on selected categories"""
    if settings is None:
        settings = {"wait_time": 10}  # Default wait time
        
    if test_categories is None:
        test_categories = ["all"]  # Run all tests by default
        
    try:
        uri = f"ws://{BACKEND_DOMAIN}:{WS_PORT}"
        print(f"Connecting to {uri}...")
        
        async with websockets.connect(uri) as websocket:
            print("Connected successfully!")

            # Map test categories to test functions
            if "all" in test_categories or "basic" in test_categories:
                await run_basic_tests(websocket, settings)
                
            if "all" in test_categories or "height" in test_categories:
                await run_height_tests(websocket, settings)
                
            if "all" in test_categories or "distance" in test_categories:
                await run_distance_tests(websocket, settings)
                
            if "all" in test_categories or "position" in test_categories:
                await run_position_reward_tests(websocket, settings)
                
            if "all" in test_categories or "behavior" in test_categories:
                await run_behavior_reward_tests(websocket, settings)
                
            if "all" in test_categories or "combined" in test_categories:
                await run_combined_reward_tests(websocket, settings)
            
            # Clean up at the end
            await clean_rewards(websocket)
            print("\nAll tests completed!")

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"\nWebSocket connection closed unexpectedly: {str(e)}")
        print("Make sure the main websocket server is running!")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        print(traceback.format_exc())

def print_test_categories():
    """Print available test categories"""
    print("\nAvailable test categories:")
    print("  all       - Run all tests")
    print("  basic     - Basic reward tests (upright, stable standing)")
    print("  height    - Height-based reward tests")
    print("  distance  - Distance-based reward tests (lateral, forward)")
    print("  position  - Position reward system tests")
    print("  behavior  - Behavior reward tests (balance, symmetry, etc.)")
    print("  combined  - Combined reward tests")

def main():
    """Main function with command-line argument parsing"""
    parser = argparse.ArgumentParser(description="Test reward functions for the Motivo system")
    parser.add_argument('--categories', '-c', nargs='+', choices=['all', 'basic', 'height', 'distance', 'position', 'behavior', 'combined'],
                        default=['all'],
                        help='Test categories to run')
    parser.add_argument('--wait', '-w', type=int, default=10,
                        help='Wait time between tests (seconds)')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List available test categories and exit')
    
    args = parser.parse_args()
    
    if args.list:
        print_test_categories()
        sys.exit(0)
    
    settings = {"wait_time": args.wait}
    
    print("Starting reward tests...")
    print("Make sure the main websocket server is running first!")
    print(f"Running test categories: {', '.join(args.categories)}")
    print(f"Wait time between tests: {args.wait} seconds")
    print("Press Ctrl+C to stop the tests at any time.")
    
    try:
        asyncio.run(run_reward_tests(args.categories, settings))
    except KeyboardInterrupt:
        print("\nTests stopped by user.")
    except Exception as e:
        print(f"\nError running tests: {str(e)}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()