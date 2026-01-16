import json
import cv2
import numpy as np
from time import sleep
from streamlink import Streamlink


config = json.load(open("config.json"))

class NeuroLamp:
    twitch_username = 'vedal987'

    x_start = config['x_start']
    x_end = config['x_end']
    y_start = config['y_start']
    y_end = config['y_end']

    lamp_ip = config['lamp_ip']
    lamp_token = config['lamp_token']

    last_color = np.array([0, 0, 0])

    update_interval = 1

    def __init__(self):
        self.stream_url = self.get_twitch_stream_url()
        self.yeelight = self.get_yeelight()


    def get_yeelight(self):
        return Yeelight(self.lamp_ip, self.lamp_token)


    def get_twitch_stream_url(self):
        """
        Get the best stream URL for the given Twitch channel using Streamlink's API.
        """
        session = Streamlink()
        try:
            streams = session.streams(f"https://www.twitch.tv/{self.twitch_username}")
            if "best" in streams:
                stream_url = streams["best"].url
                print(f"Stream URL: {stream_url}")
                return stream_url
            else:
                print("No 'best' stream available.")
                return None
        except Exception as e:
            print(f"Failed to get stream URL: {e}")
            return None


    # In GPT I trust
    def get_important_pixels(self, frame):
        """
        Find the brightest color and the color furthest from gray (excluding near black/white) in a rectangle at the bottom-right of the frame.
        """
        print(f"Saving debug frame.png")
        cv2.imwrite("frame.png", frame)

        roi = frame[self.y_start:self.y_end, self.x_start:self.x_end]

        print(f"Saving debug rectangle.png")
        cv2.imwrite("rectangle.png", roi)
        
        # Round each pixel's color values to the nearest multiple of 10
        roi_reshaped = roi.reshape(-1, 3)
        rounded_colors = (np.round(roi_reshaped / 5) * 5).astype(int)
        
        # Find the most occurring color
        unique_colors, counts = np.unique(rounded_colors, axis=0, return_counts=True)
        most_occurring_color = unique_colors[np.argmax(counts)]
        # Values in array are reversed (bgr -> rgb)
        most_occurring_color = [int(f) for f in most_occurring_color[::-1]]
        
        # Calculate brightness as a percentage of closeness to white
        brightness_percentage = (np.linalg.norm(most_occurring_color) / np.linalg.norm([255, 255, 255])) * 100
        
        self.last_color = most_occurring_color
        return most_occurring_color, brightness_percentage



    def get_lavalamp_color(self, frame):
        color, brightness = self.get_important_pixels(frame)

        # TODO: this is currently useless
        brightness = 100

        return brightness, color


    def run(self):
        while True:
            print("Capturing new frame")
            cap = cv2.VideoCapture(self.stream_url)
            if not cap.isOpened():
                print("Error: Unable to open the stream.")
                return

            ret, frame = cap.read()
            if ret:
                brightness, color = self.get_lavalamp_color(frame)
                self.update_lamp(brightness, color)

            else:
                print("Error: Unable to capture a frame.")

            # Release the video capture object
            cap.release()

            sleep(self.update_interval)


    def update_lamp(self, brightness, rgb):
        print(f"Brightness: {brightness}, RGB: {rgb}")
        if brightness < 1 or brightness > 100:
            print("Invalid brightness value")
            return
        if any([c < 1 or c > 255 for c in rgb]):
            print("Invalid RGB value, defaulting to brightness")
            rgb = [brightness] * 3
        self.yeelight.set_brightness(brightness)
        self.yeelight.set_rgb(rgb)



if __name__ == "__main__":
    lamp = NeuroLamp()
    lamp.run()