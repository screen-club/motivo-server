import cv2
import numpy as np
from typing import Optional
import os

class DisplayManager:
    def __init__(self, window_name: str = "Humanoid Simulation", headless: bool = False):
        self.window_name = window_name
        self.headless = headless
        
        # Only create window if not in headless mode
        if not self.headless:
            try:
                cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(self.window_name, 800, 600)
                print("Created display window successfully")
            except Exception as e:
                print(f"Failed to create display window, switching to headless mode: {e}")
                self.headless = True
        
        # Initialize font
        # Try to load a specific font file if available
        font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'DejaVuSans.ttf')
        if os.path.exists(font_path):
            self.font = cv2.FONT_HERSHEY_DUPLEX  # Fallback to built-in font
        else:
            self.font = cv2.FONT_HERSHEY_SIMPLEX  # Use default font
        
        print(f"DisplayManager initialized in {'headless' if self.headless else 'display'} mode")
            
    def show_frame(self, 
                   frame: np.ndarray, 
                   q_percentage: Optional[float] = None,
                   is_computing: bool = False,
                   resize_dims: tuple = (1280, 960)) -> np.ndarray:
        """
        Display and process a frame with optional overlays
        
        Args:
            frame: Original frame to display
            q_percentage: Quality percentage to display (0-100)
            is_computing: Whether reward computation is in progress
            resize_dims: Dimensions for the saved frame (default: 1280x960)
            
        Returns:
            Processed frame with overlays for saving or streaming
        """
        if frame is None:
            # Create a blank frame as fallback to prevent NoneType errors
            blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            text = "No frame available"
            cv2.putText(
                blank_frame,
                text,
                (100, 240),
                self.font,
                1.0,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )
            return blank_frame
            
        try:
            # Ensure frame is in the correct format
            if frame.dtype != np.uint8:
                frame = (frame * 255).astype(np.uint8)
            
            # Use the original frame directly with minimal processing
            display_frame = frame.copy()
            
            # The environment returns frames in RGB format
            # We need to convert to BGR for OpenCV display functions
            if len(display_frame.shape) == 3 and display_frame.shape[2] == 3:
                # Debug log (first few frames)
                if not hasattr(self, "_debug_count"):
                    self._debug_count = 0
                
                if self._debug_count < 3:
                    print(f"Display frame before conversion: shape={display_frame.shape}, "
                          f"dtype={display_frame.dtype}, min={display_frame.min()}, "
                          f"max={display_frame.max()}")
                    self._debug_count += 1
                
                # Convert from RGB to BGR for OpenCV display
                display_frame = cv2.cvtColor(display_frame, cv2.COLOR_RGB2BGR)
            
            # Add Q-value overlay with better visibility
            if q_percentage is not None:
                # Draw text with background for better visibility
                text = f"Quality: {q_percentage:.1f}%"
                font_scale = 0.7
                thickness = 1  # Reduced thickness for better anti-aliasing
                font = self.font
                
                # Get text size
                (text_width, text_height), baseline = cv2.getTextSize(
                    text, font, font_scale, thickness
                )
                
                # Calculate text background rectangle
                padding = 5
                text_x, text_y = 10, 30
                cv2.rectangle(
                    display_frame,
                    (text_x - padding, text_y - text_height - padding),
                    (text_x + text_width + padding, text_y + padding),
                    (0, 0, 0),
                    -1
                )
                
                # Draw text with anti-aliasing
                cv2.putText(
                    display_frame,
                    text,
                    (text_x, text_y),
                    font,
                    font_scale,
                    (255, 255, 255),
                    thickness,
                    cv2.LINE_AA  # Enable anti-aliasing
                )
            
            # Add computing indicator with background
            if is_computing:
                text = "Computing rewards..."
                font_scale = 0.6
                thickness = 1
                font = self.font
                
                # Get text size
                (text_width, text_height), baseline = cv2.getTextSize(
                    text, font, font_scale, thickness
                )
                
                # Calculate text background rectangle
                padding = 5
                text_x, text_y = 10, 60
                cv2.rectangle(
                    display_frame,
                    (text_x - padding, text_y - text_height - padding),
                    (text_x + text_width + padding, text_y + padding),
                    (0, 0, 0),
                    -1
                )
                
                # Draw text with anti-aliasing
                cv2.putText(
                    display_frame,
                    text,
                    (text_x, text_y),
                    font,
                    font_scale,
                    (255, 255, 0),  # Yellow text
                    thickness,
                    cv2.LINE_AA  # Enable anti-aliasing
                )
            
            # Only show the frame if not in headless mode
            if not self.headless:
                try:
                    cv2.imshow(self.window_name, display_frame)
                except Exception as e:
                    print(f"Failed to show frame, continuing in headless mode: {e}")
                    self.headless = True
            
            # Create resized version for saving - use high quality interpolation
            if display_frame.shape[0] != resize_dims[1] or display_frame.shape[1] != resize_dims[0]:
                resized_frame = cv2.resize(
                    display_frame, 
                    resize_dims, 
                    interpolation=cv2.INTER_LANCZOS4  # Use high quality interpolation
                )
            else:
                resized_frame = display_frame.copy()
            
            return resized_frame
            
        except Exception as e:
            print(f"Error in show_frame: {str(e)}")
            # Return a blank frame with error message instead of None
            blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                blank_frame,
                f"Error: {str(e)}",
                (50, 240),
                self.font,
                0.7,
                (0, 0, 255),
                1,
                cv2.LINE_AA
            )
            return blank_frame
    
    def check_key(self) -> tuple[bool, bool]:
        """
        Check for key presses
        
        Returns:
            Tuple of (should_quit, should_save)
        """
        if self.headless:
            return False, False
            
        try:
            key = cv2.waitKey(1) & 0xFF
            should_quit = key == 27  # ESC
            should_save = key == ord('s')
            return should_quit, should_save
        except Exception as e:
            print(f"Error in check_key: {str(e)}")
            # If we encounter an error, switch to headless mode
            self.headless = True
            return False, False
    
    def cleanup(self):
        """Clean up OpenCV windows"""
        if self.headless:
            return
            
        try:
            cv2.destroyAllWindows()
            for i in range(4):
                cv2.waitKey(1)
        except Exception as e:
            print(f"Error in cleanup: {str(e)}")
            self.headless = True 