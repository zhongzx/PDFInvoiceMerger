from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QRect
import sys
import os

def create_app_icon():
    size = 256
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw Background (Document shape)
    margin = 40
    doc_rect_1 = QRect(margin, margin, size - 2*margin, size - 2*margin)
    
    # Draw "Merged" effect
    # Top Half (Blue-ish)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#4682B4"))) # SteelBlue
    top_rect = QRect(margin, margin, size - 2*margin, (size - 2*margin)//2)
    painter.drawRoundedRect(top_rect, 20, 20, Qt.SizeMode.AbsoluteSize)
    
    # Bottom Half (Darker Blue)
    painter.setBrush(QBrush(QColor("#2F4F4F"))) # DarkSlateGray
    bottom_rect = QRect(margin, margin + (size - 2*margin)//2, size - 2*margin, (size - 2*margin)//2)
    # We need to draw the bottom corners rounded, but top corners square for the join
    # Simpler: just draw a rect and then a rounded one? 
    # Let's just draw two overlapping docs
    
    # Clear and redraw a better concept: Two documents merging
    image.fill(Qt.GlobalColor.transparent)
    
    # Document 1 (Back)
    painter.setBrush(QBrush(QColor("#B0C4DE"))) # LightSteelBlue
    painter.drawRoundedRect(60, 40, 140, 180, 10, 10)
    
    # Document 2 (Front)
    painter.setBrush(QBrush(QColor("#4682B4"))) # SteelBlue
    painter.drawRoundedRect(80, 60, 140, 180, 10, 10)
    
    # "Merge" Arrow/Symbol
    painter.setPen(QPen(Qt.GlobalColor.white, 8))
    painter.drawLine(150, 130, 150, 170)
    painter.drawLine(130, 150, 170, 150)
    
    painter.end()
    
    output_path = os.path.join("assets", "icon.png")
    image.save(output_path)
    print(f"Icon saved to {output_path}")

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    create_app_icon()
