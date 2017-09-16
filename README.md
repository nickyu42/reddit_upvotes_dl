# Reddit upvoted downloader
Logs into reddit and grabs all the image links from the specified subreddits (in the .json file)
into the directory specified in the same subreddits.json file
## Requirements

- Python 3.6+
- `requests` library
- `lxml` library

## Example subreddits.json file
```
{
  "C:\\Users\\Foo\\Pictures": 
    [
    "animeponytails",
    "awwnime",
    "cutelittlefangs"
    ],

  "C:\\Users\\Foo\\Pictures\\Wallpapers": 
    [
    "MinimalWallpaper",
    "wallpapers"
    ]
}
```
