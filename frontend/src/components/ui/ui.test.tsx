import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Alert, AlertDescription, AlertTitle } from "./alert";
import { Button } from "./button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./dialog";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
  FieldTitle,
} from "./field";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
  InputGroupTextarea,
} from "./input-group";
import { Input } from "./input";
import { Label } from "./label";
import { Separator } from "./separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";
import { Textarea } from "./textarea";

describe("ui components", () => {
  it("renders and clicks buttons", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);

    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).toHaveBeenCalled();
  });

  it("renders form controls", async () => {
    render(
      <div>
        <Label htmlFor="name">Name</Label>
        <Input id="name" placeholder="Name" />
        <Textarea placeholder="Notes" />
      </div>,
    );

    await userEvent.type(screen.getByLabelText("Name"), "Alex");
    await userEvent.type(screen.getByPlaceholderText("Notes"), "Details");
    expect(screen.getByLabelText("Name")).toHaveValue("Alex");
    expect(screen.getByPlaceholderText("Notes")).toHaveValue("Details");
  });

  it("renders alert and card primitives", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Card title</CardTitle>
          <CardDescription>Card description</CardDescription>
        </CardHeader>
        <CardContent>
          <Alert>
            <AlertTitle>Heads up</AlertTitle>
            <AlertDescription>Alert body</AlertDescription>
          </Alert>
        </CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>,
    );

    expect(screen.getByText("Card title")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Alert body");
    expect(screen.getByText("Footer")).toBeInTheDocument();
  });

  it("opens and closes dialogs", async () => {
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Open dialog</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Dialog title</DialogTitle>
            <DialogDescription>Dialog description</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Open dialog" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Dialog title");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("switches tab content", async () => {
    render(
      <Tabs defaultValue="one">
        <TabsList>
          <TabsTrigger value="one">One</TabsTrigger>
          <TabsTrigger value="two">Two</TabsTrigger>
        </TabsList>
        <TabsContent value="one">First panel</TabsContent>
        <TabsContent value="two">Second panel</TabsContent>
      </Tabs>,
    );

    expect(screen.getByText("First panel")).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "Two" }));
    expect(screen.getByText("Second panel")).toBeVisible();
  });

  it("renders field, separator, and input-group helpers", async () => {
    render(
      <FieldSet>
        <FieldLegend>Profile</FieldLegend>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <FieldContent>
              <FieldTitle>Email title</FieldTitle>
              <FieldDescription>Email description</FieldDescription>
              <InputGroup>
                <InputGroupAddon>
                  <InputGroupText>@</InputGroupText>
                </InputGroupAddon>
                <InputGroupInput id="email" aria-label="Email" />
                <InputGroupButton>Go</InputGroupButton>
              </InputGroup>
              <InputGroup>
                <InputGroupTextarea aria-label="Long text" />
              </InputGroup>
              <FieldError errors={[{ message: "Required" }]} />
            </FieldContent>
          </Field>
          <FieldSeparator>or</FieldSeparator>
          <Separator />
        </FieldGroup>
      </FieldSet>,
    );

    await userEvent.type(screen.getByLabelText("Email"), "person@example.com");
    expect(screen.getByText("Profile")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("person@example.com");
  });

  it("covers alternate helper branches", async () => {
    render(
      <div>
        <Button asChild>
          <a href="/next">Link button</a>
        </Button>
        <InputGroup>
          <InputGroupAddon>
            <InputGroupButton>Nested</InputGroupButton>
          </InputGroupAddon>
          <InputGroupInput aria-label="Focusable input" />
        </InputGroup>
        <FieldError
          errors={[
            { message: "First" },
            { message: "Second" },
            { message: "First" },
          ]}
        />
        <FieldError>Custom error</FieldError>
        <FieldError errors={[]} />
      </div>,
    );

    expect(screen.getByRole("link", { name: "Link button" })).toHaveAttribute(
      "href",
      "/next",
    );
    await userEvent.click(screen.getByText("Nested"));
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
    expect(screen.getByText("Custom error")).toBeInTheDocument();
  });
});
