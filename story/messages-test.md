---
revisit: false
choices:
    - label: How can I change the text speed
      to: speed-test
    - label: How can I apply text effects
      to: effect-test
    - label: How to make POV explicitly clear
      to: pov-test
    - label: How can I show messages between people
      to: messages-test
    - label: How can I visually show the weather at that time
      to: weather-test
    - label: How can I add extra background effects
      to: background-effects
    - label: How can I show a background image
      to: images-test
    - label: How can I play music and sound effects
      to: audio-test
    - label: How can I make the story remember choices
      to: flags-test
    - label: How do saves and the back button work
      to: back-save-test
    - label: How do I change how the story looks and feels
      to: settings-test
    - label: Open the page only a flag can reach
      to: flags-unlocked
      if: flags-demo-seen
    - label: What happens to a choice with no implementation
      to: not-done
    - label: What about when I end the story
      to: end
message-pov: You
---

This is a demonstration of how to show messages in a chat, if you want

You just add `/message (name)` in front of a line, and you're good to go!

/message You this is a pretty cool message

/message author I would say so yes

/message You You can send multiple messages in series

/message You see how it stacks very nicely with multiple messages

/message You and you can even write a lot of things and hope for the best that it will oroperly be resized and wrap around lines, oh look, it does!

we can split up messages with regular text

The colours of messages mirror the POV colours for every speaker, so make sure to add that to the `povColours` config option if you don't want it chosen randomly!

/message author2 you can even have group chats of a sort

/message author wow, that's cool

/message-unsent You What about a message I've typed but not sent, how will I show that? Well, `message-unsent` will show that!

by default the POV of the messages will be the owner of the first message.

If, however, you would like to change that, you can assign the `message-pov: (namme)` metadata to the story. the same works with `pov: (name)` metadata too.

the `/message-unsent (name)` command will only work for the message-pov person (as other people in a conversation can't see what you haven't sent!)

/message-title fun chat time

/message author2 You can even title the messages if you want

/message author you just have to add `/message-title (title)` before the group

/message You however, this will only carry to the next messages list, so you'll have to redefine it every single time

/message author2 Unless, of course, you specify message-title in the story metadata, where that will be used if none is given!
